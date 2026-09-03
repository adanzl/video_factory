# AI辅助信息

## SSH

主机名：

- 局域网 主机: mini  
- 广域网 主机：vip.sy.frp.one:57904
- 广域网 主机：cn-hk-bgp-4.ofalias.net:27358
用户名 leo
密码 见.env 里的 SSH_PASSWORD
优先级从上到下

StableDiffusion 目录 /mnt/data/stable-diffusion/webui
sd日志查询 journalctl -u sd.service -f

## 项目

- 目录：/mnt/data/project/video_factory
- 服务 video-factory

## 服务器硬件

``` TEXT
CPU: AMD Ryzen 9 7940HS w/ Radeon 780M Graphics
- 16 逻辑核心 (8 核 16 线程), 最大频率 5.26 GHz
- L1 缓存 512 KiB, L2 缓存 8 MiB, L3 缓存 16 MiB
内存: 28 GiB
- Swap: 19 GiB 
显卡: AMD Radeon 780M (Phoenix1, 集成显卡), 无独立 NVIDIA 显卡
- 共享显存为 3 GiB（3221225472 bytes），从系统内存中划分。
```

## 网络

网络 无法连接 Civitai
可以访问 liblib.art

## Python 环境

使用 **conda**，env: flask_env，不要再说本地没python了

## 「专家」

- DeepSeek 网页模拟 API
- 涉及提示词方案评审时用户说「和专家商量/达成一致再落地」，指用它的专家模式评审
- body `{"question":..., "mode":"expert", "deep_thinking":true}`
- 新对话不带 `conversation_id`，续聊带返回 id
- 除非特别短的问题，否则使用异步模式

### 接口

- Deepseek 说明 `POST http://xxx/api/deepseek/doc`
- 千问 说明 `POST http://xxx/api/qwen/doc`
- Agnes 说明 `POST http://xxx/api/agnes/doc`
- ChatGPT 说明 `POST http://xxx/api/chatgpt/doc`

### 状态查

 `GET /api/deepseek/status`
 `GET /api/qwen/status`
 `GET /api/agnes/status`
 `GET /api/chatgpt/status`

### 地址

- 优先级从上到下
- <http://127.0.0.1:8848/> (有ChatGPT)（url里没有mock_agent）
- <http://192.168.50.172:8848/mock_agent>
- <https://leo-zhao.natapp4.cc/mock_agent>

### 专家模式 + 深度思考 （千问没有专家模式）

```json
{
  "question": "证明根号2是无理数",
  "mode": "expert",  // 千问 不传
  "deep_thinking": true,
  "timeout": 600   // 超时【秒】
}
```

### 成功响应

```json
{
  "ok": true,
  "question": "...",
  "answer": "...",
  "conversation_id": "uuid",
  "mode": "instant",
  "deep_thinking": true,
  "search": false,
  "url": "https://chat.deepseek.com/a/chat/s/uuid"
}
```

### 续聊并保持选项

```json
{
  "conversation_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "question": "把证明写得更短一些",
  "mode": "expert",
  "deep_thinking": true
}
```

## 注意

- 重跑任务需要我明确提出了才进行，如果你想重跑需要我二次确认
- 创建的临时文件记得删除
- 重启服务要找我确认
- **变量定义注意拼写，避免cSpell告警**
- 新建独立文件要找我二次确认，没必要不要做
- 使用Tailwind
- 我让你查数据 先从远程服务器上查
- 给出的回答要有根据，别瞎猜
- 除非特殊说明，日志和数据都去查远程的
- 你要是说服务器就旧代码先去服务器上查git记录再说
- 要测试先本地测通过了再推送，除非我要求，不要远程测试
- PowerShell 会拆坏命令，不要直接用，用 Python
- 生成故事要和DB已有作比较，避免重复
- 生图和生视频提示词由 Agnes mock审核
- 不能上传db文件
- 避免 Emphasis used instead of a heading
- 避免代码告警 不能有basedpyright报错
- gevent thread=False  下不要使用 threading.Lock

## 审核稿子

- 3家审核表示：专家 mock、qwen mock、你 审核
- setting用户看不到，有些矛盾可忽略
- 给mock的对话，同一类问题不要新开对话
- 不要过拟合
- 图片、视频生成的提示词修改问agnes mock
- 你要是看图的话，用Agnes Vl

## 快捷命令

- push 表示执行提交git 并执行push，不用你管远程pull的事
- pull 表示执行本地git pull，并解决本地冲突
- 不要自动push，需要我同意才行

## pi插件

- pi-agent-extensions、 17 个扩展和 4 种主题
    `pi install npm:pi-agent-extensions`
- pi-mcp-adapter
    `pi install npm:pi-mcp-adapter`
- pi-background-tasks 允许你在后台运行耗时的 Shell 任务，避免阻塞主会话
    `pi install npm:@ifi/pi-background-tasks'
- pi-web-access 赋予 Pi 网页搜索、URL 抓取、GitHub 仓库克隆等能力
    `pi install npm:pi-web-access`

## 专家接口调通方案（2026-09-02）

**问题**：异步深度思考模式经常超时或无响应，后台 curl 子进程难以捕获输出。

**解决方案**：使用 instant 模式（无深度思考）直接同步调用。

```bash
# ✅ 有效的方式：instant 模式 + 同步 curl
curl -s -X POST http://127.0.0.1:8848/api/deepseek/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "你的问题",
    "mode": "instant",
    "timeout": 30
  }' | python3 -m json.tool
```

**关键点**：

- `mode: "instant"` 替代 `mode: "expert" + deep_thinking: true`
- 不用异步后台，直接同步等待（一般 15-25 秒返回）
- 响应格式完全相同（包含 answer、conversation_id 等），可用于续聊

**续聊**（如需深化）：

```json
{
  "conversation_id": "前次返回的 uuid",
  "question": "后续问题",
  "mode": "instant"
}
```

**实测**：M8+J 字数稳定优化（E+B 两项）通过本地 E2E 测试（5/5 通过，100% 成功率），字数 242~251 稳定过线。
