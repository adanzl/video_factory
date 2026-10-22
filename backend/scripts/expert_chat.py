"""专家对话：代替网页端 DeepSeek 模拟接口，直接走已配置的 LLM。

用来评审「稿子生成代码」怎么改。同一 conversation_id 续聊，不新开话题。

用法（在 backend 目录）::

    python -m scripts.expert_chat --question-file brief.md
    python -m scripts.expert_chat --conversation-id <id> --question "阈值改成 4 呢"
    python -m scripts.expert_chat --last --question "接着上回那条继续"
    python -m scripts.expert_chat --print-prompt --file line.py --question "看这条机检"
    python -m scripts.expert_chat --no-thinking --max-tokens 16384 --question "..."
    python -m scripts.expert_chat

无参数时进入多轮对话。/exit 退出，/new 换一个新对话。
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings

DEFAULT_SESSION = ROOT_DIR / "data" / "expert_sessions.json"

# 发给模型的历史：按条数 + 字符双限，超出从最早一对开始丢
MAX_HISTORY_MESSAGES = 16
MAX_HISTORY_CHARS = 48000
# 落盘保留的条数（比发出去的多，便于回看），超了从头裁
MAX_SESSION_MESSAGES = 60

# 单文件摘录：行数 + 字符双限，按行截断并带行号，方便专家按行指位置
FILE_EXCERPT_LINES = 240
FILE_EXCERPT_CHARS = 8000
# 单条消息的附件总量预算
MAX_ATTACH_CHARS = 40000
MAX_QUESTION_CHARS = 24000

SYSTEM_PROMPT = """你评审稿子生成代码该怎么改。只根据用户这次贴出的现象、代码和方案说话。

直接下判断，不要复述题面，不要顺着方案圆。
机检只写换一篇戏仍成立的不变量，禁止按单篇剧情或台词词表写规则。
提示词管写法，机检管能程序判定的失败，要读完全文才能定的交给终检。
不要建议手改成稿。用户按条提问就按条答。"""


class ExpertError(RuntimeError):
    """专家对话调用失败。"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def excerpt(text: str, limit: int) -> str:
    """超长文本保留头尾，避免整文件塞进对话。"""
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return text[:head] + "\n……（中间略）……\n" + text[-tail:]


def excerpt_file(text: str, *, max_lines: int = FILE_EXCERPT_LINES) -> str:
    """按行摘录并加行号：超长时保留头 60% / 尾 40% 行，中间标注省略区间。

    带行号是为了专家能说「第 3 条规则」而不是「靠后那段」。
    """
    lines = text.splitlines()
    if len(lines) <= max_lines:
        numbered = [f"{no:>4}| {line}" for no, line in enumerate(lines, start=1)]
        return "\n".join(numbered)
    head_n = max_lines * 3 // 5
    tail_n = max_lines - head_n
    tail_start = len(lines) - tail_n + 1
    numbered = [f"{no:>4}| {line}" for no, line in enumerate(lines[:head_n], start=1)]
    numbered.append(
        f"……（省略第 {head_n + 1}-{tail_start - 1} 行，共 {tail_start - head_n - 1} 行）……"
    )
    numbered.extend(
        f"{no:>4}| {line}"
        for no, line in enumerate(lines[tail_start - 1 :], start=tail_start)
    )
    return "\n".join(numbered)


def _read_text_file(path: Path) -> str:
    if not path.is_file():
        raise ExpertError(f"文件不存在: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ExpertError(f"文件不是 UTF-8 文本: {path}") from exc
    except OSError as exc:
        raise ExpertError(f"读文件失败: {path} ({exc})") from exc


def compose_user_message(question: str, files: list[Path]) -> str:
    """把问题和附件收成一条用户消息。"""
    text = question.strip()
    if len(text) > MAX_QUESTION_CHARS:
        dropped = len(text) - MAX_QUESTION_CHARS
        text = excerpt(text, MAX_QUESTION_CHARS) + f"\n\n（问题超长，已省略 {dropped} 字）"
    parts = [text]
    per_file = min(FILE_EXCERPT_CHARS, MAX_ATTACH_CHARS // max(1, len(files)))
    for path in files:
        raw = _read_text_file(path)
        body = excerpt_file(raw)
        if len(body) > per_file:
            body = excerpt(body, per_file)
        parts.append(f"【文件】{path.as_posix()}\n```\n{body}\n```")
    message = "\n\n".join(part for part in parts if part)
    if not message:
        raise ExpertError("问题是空的")
    return message


def _align_pairs(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """裁掉开头的孤儿 assistant，保证历史从 user 起头。"""
    trimmed = list(messages)
    while trimmed and trimmed[0]["role"] != "user":
        trimmed.pop(0)
    return trimmed


def trim_history(
    messages: list[dict[str, str]],
    *,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_chars: int = MAX_HISTORY_CHARS,
) -> list[dict[str, str]]:
    """按条数与字符双限裁历史；从头丢，且不让 assistant 消息打头。"""
    kept = list(messages)
    while kept:
        total_chars = sum(len(item["content"]) for item in kept)
        if (
            len(kept) <= max_messages
            and total_chars <= max_chars
            and kept[0]["role"] == "user"
        ):
            break
        if len(kept) == 1:
            only = kept[0]
            if only["role"] == "user" and len(only["content"]) > max_chars:
                kept[0] = {**only, "content": only["content"][-max_chars:]}
            else:
                kept.clear()
            break
        kept.pop(0)
    return kept


def build_messages(history: list[dict[str, str]], question: str) -> list[dict[str, str]]:
    """系统提示词每次现拼，不写进会话文件，改口径后旧对话也能用上。"""
    kept = trim_history(history)
    system = SYSTEM_PROMPT
    omitted = len(history) - len(kept)
    if omitted > 0:
        system = f"{system}\n\n（更早的 {omitted} 条历史已省略，需要时请用户补。）"
    return [
        {"role": "system", "content": system},
        *kept,
        {"role": "user", "content": question},
    ]


def load_session(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"conversations": {}}
    raw = _read_text_file(path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExpertError(f"会话文件不是合法 JSON: {path} ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("conversations"), dict):
        raise ExpertError(f"会话文件损坏: {path}")
    return data


def save_session(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        raise ExpertError(f"写会话文件失败: {path} ({exc})") from exc


def latest_conversation_id(data: dict[str, Any]) -> str | None:
    """取最近一次落盘更新的对话（旧文件没 updated_at 时按插入顺序取最后一条）。"""
    conversations = data.get("conversations")
    if not isinstance(conversations, dict) or not conversations:
        return None
    scored: list[tuple[str, int, str]] = []
    for index, (cid, payload) in enumerate(conversations.items()):
        stamp = ""
        if isinstance(payload, dict):
            stamp = str(payload.get("updated_at") or "")
        scored.append((stamp, index, str(cid)))
    return max(scored)[2]


def history_of(data: dict[str, Any], conversation_id: str) -> list[dict[str, str]]:
    raw = data["conversations"].get(conversation_id) or {}
    messages = raw.get("messages") if isinstance(raw, dict) else None
    if not isinstance(messages, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            cleaned.append({"role": role, "content": content})
    return cleaned


def extract_answer(payload: dict[str, Any], *, max_tokens: int) -> tuple[str, str]:
    """从 chat/completions 响应取出正文。"""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExpertError(f"LLM 响应没有 choices: {str(payload)[:300]}")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ExpertError("LLM 响应 choices[0] 不是对象")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ExpertError("LLM 响应没有 message")
    content = message.get("content")
    finish = str(choice.get("finish_reason") or "")
    if isinstance(content, str) and content.strip():
        return content.strip(), finish
    if finish == "length":
        raise ExpertError(
            f"思考 token 已吃满 max_tokens={max_tokens}，正文没出来。"
            "加大 --max-tokens，或加 --no-thinking 关思考。"
        )
    raise ExpertError(f"LLM 没有返回正文 finish_reason={finish or '空'}")


def _resolve_target(*, model: str | None, max_tokens: int | None) -> tuple[str, int]:
    """按当前 LLM_PROVIDER 推算 (显示用模型名, 输出额度)，与 provider 内部默认保持一致。"""
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "agnes":
        default_model = settings.agnes_llm_model
        default_limit = settings.agnes_llm_max_tokens
    elif provider == "opencode_go":
        default_model = settings.deepseek_pro_model or settings.deepseek_model
        default_limit = settings.deepseek_max_tokens
    else:
        default_model = settings.deepseek_pro_model or settings.deepseek_model
        default_limit = settings.deepseek_max_tokens
    return model or default_model, int(max_tokens or default_limit)


def complete(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    max_tokens: int | None = None,
    thinking: bool | None = None,
) -> tuple[str, str, str, int]:
    """走 llm_mgr 的多轮对话，返回 (正文, finish_reason, 模型, 额度)。

    传输层（重试 / key 兜底 / 域名切换）由各 provider 自己负责，
    这里只把异常收口成 ExpertError，并补齐「有 finish_reason 但正文为空」的说明。
    """
    from app.services.llm.llm_mgr import llm_mgr

    if not get_settings().text_llm_configured():
        missing = "、".join(get_settings().missing_provider_keys()) or "LLM Key"
        raise ExpertError(f"当前 LLM_PROVIDER 未配置 Key：{missing}")
    use_model, limit = _resolve_target(model=model, max_tokens=max_tokens)
    try:
        answer, finish = llm_mgr.chat_messages(
            messages,
            max_tokens=limit,
            thinking_enabled=thinking,
            model=model,
        )
    except Exception as exc:
        raise ExpertError(f"LLM 调用失败：{type(exc).__name__}: {exc}") from exc
    text = (answer or "").strip()
    if not text:
        if finish == "length":
            raise ExpertError(
                f"思考 token 已吃满 max_tokens={limit}，正文没出来。"
                "加大 --max-tokens，或加 --no-thinking 关思考。"
            )
        raise ExpertError(f"LLM 没有返回正文 finish_reason={finish or '空'}")
    return text, str(finish or ""), use_model, limit


def ask(
    question: str,
    *,
    conversation_id: str | None = None,
    files: list[Path] | None = None,
    session_path: Path = DEFAULT_SESSION,
    new_conversation: bool = False,
    model: str | None = None,
    max_tokens: int | None = None,
    thinking: bool | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """问一轮，并按 conversation_id 续写本地会话。"""
    user_text = compose_user_message(question, files or [])
    data = load_session(session_path)
    if new_conversation and conversation_id:
        raise ExpertError("--new 与 --conversation-id 不能同时用；要续聊就别加 --new")
    if new_conversation or not conversation_id:
        conversation_id = uuid.uuid4().hex
        history: list[dict[str, str]] = []
    else:
        history = history_of(data, conversation_id)
        if not history:
            raise ExpertError(
                f"会话 {conversation_id} 在 {session_path} 里没有记录；"
                "核对 id，或用 --last 续最近一次，或加 --new 新开"
            )
    messages = build_messages(history, user_text)
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "conversation_id": conversation_id,
            "question": user_text,
            "messages": messages,
            "prompt_chars": sum(len(item["content"]) for item in messages),
        }
    answer, finish, used_model, limit = complete(
        messages,
        model=model,
        max_tokens=max_tokens,
        thinking=thinking,
    )
    stored = _align_pairs(history + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": answer},
    ])[-MAX_SESSION_MESSAGES:]
    data["conversations"][conversation_id] = {
        "messages": stored,
        "updated_at": _now_iso(),
        "model": used_model,
        "turns": len(stored) // 2,
    }
    save_session(session_path, data)
    return {
        "ok": True,
        "question": user_text,
        "answer": answer,
        "conversation_id": conversation_id,
        "finish_reason": finish,
        "model": used_model,
        "max_tokens": limit,
    }


def _read_question(args: argparse.Namespace) -> str:
    chunks: list[str] = []
    if args.question_file:
        chunks.append(_read_text_file(Path(args.question_file)))
    if args.question:
        chunks.append(args.question)
    if not chunks and not sys.stdin.isatty():
        chunks.append(sys.stdin.read())
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def _print_result(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"conversation_id: {result['conversation_id']}\n")
    print(result["answer"])
    if result.get("finish_reason") == "length":
        print("\n（回答被长度截断，可用 --max-tokens 放宽）", file=sys.stderr)


def _print_prompt(result: dict[str, Any]) -> None:
    messages = result.get("messages") or []
    print(f"conversation_id: {result['conversation_id']}")
    print(f"messages: {len(messages)} 条，共 {result.get('prompt_chars', 0)} 字符\n")
    for item in messages:
        role = item.get("role", "?")
        body = item.get("content", "")
        print(f"===== {role} ({len(body)} 字符) =====")
        print(body)
        print()


def _resolve_conversation_id(args: argparse.Namespace) -> str | None:
    """--last 从会话文件取最近一次；与 --conversation-id 同时用直接报错。"""
    explicit = (args.conversation_id or "").strip() or None
    if args.last and explicit:
        raise ExpertError("--last 与 --conversation-id 不能同时用")
    if not args.last:
        return explicit
    latest = latest_conversation_id(load_session(Path(args.session)))
    if not latest:
        raise ExpertError(f"{args.session} 里还没有对话，先问一轮")
    return latest


def _repl(args: argparse.Namespace) -> int:
    conversation_id = None if args.new else _resolve_conversation_id(args)
    print("专家对话。/exit 退出，/new 新开对话。")
    if conversation_id:
        print(f"续聊 {conversation_id}")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line == "/exit":
            return 0
        if line == "/new":
            conversation_id = None
            print("已新开对话")
            continue
        try:
            result = ask(
                line,
                conversation_id=conversation_id,
                session_path=Path(args.session),
                model=args.model or None,
                max_tokens=args.max_tokens,
                thinking=False if args.no_thinking else None,
            )
        except ExpertError as exc:
            print(str(exc), file=sys.stderr)
            continue
        conversation_id = str(result["conversation_id"])
        _print_result(result, as_json=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="专家对话（代替网页端模拟接口）")
    parser.add_argument("--question", default="", help="这一轮的问题")
    parser.add_argument("--question-file", default="", help="问题 Markdown 文件")
    parser.add_argument("--file", action="append", default=[], help="附上的代码文件，可重复")
    parser.add_argument("--conversation-id", default="", help="续聊已有对话；不传则新开")
    parser.add_argument("--last", action="store_true", help="续最近一次对话")
    parser.add_argument("--new", action="store_true", help="忽略已有记录，新开对话")
    parser.add_argument("--model", default="", help="覆盖模型（默认取 DEEPSEEK_PRO_MODEL）")
    parser.add_argument("--max-tokens", type=int, default=0, help="覆盖输出额度")
    parser.add_argument("--no-thinking", action="store_true", help="关掉深度思考")
    parser.add_argument("--print-prompt", action="store_true", help="只打印将发送的消息，不发请求")
    parser.add_argument("--json", action="store_true", help="按网页接口的 JSON 形状输出")
    parser.add_argument("--session", default=str(DEFAULT_SESSION), help="本地会话文件")
    args = parser.parse_args(argv)

    try:
        if args.print_prompt:
            question = _read_question(args)
            if not question:
                raise ExpertError("--print-prompt 需要 --question 或 --question-file")
            dry = ask(
                question,
                conversation_id=None,
                files=[Path(item) for item in args.file],
                session_path=Path(args.session),
                new_conversation=args.new,
                dry_run=True,
            )
            _print_prompt(dry)
            return 0

        question = _read_question(args)
        if not question:
            if args.json:
                print("没有问题。交互对话不要加 --json", file=sys.stderr)
                return 1
            return _repl(args)
        result = ask(
            question,
            conversation_id=_resolve_conversation_id(args),
            files=[Path(item) for item in args.file],
            session_path=Path(args.session),
            new_conversation=args.new,
            model=args.model or None,
            max_tokens=args.max_tokens or None,
            thinking=False if args.no_thinking else None,
        )
    except ExpertError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_result(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
