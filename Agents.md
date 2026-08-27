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

DeepSeek 网页模拟 API，不是 Claude 子代理。涉及提示词方案评审时用户说「和专家商量/达成一致再落地」，指用它的专家模式评审。body `{"question":..., "mode":"expert", "deep_thinking":true}`；新对话不带 `conversation_id`，续聊带返回 id；

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

## 审核稿子

- 3家审核表示：专家 mock、qwen mock、你 审核
- setting用户看不到，有些矛盾可忽略
- 给mock的对话，同一类问题不要新开对话
- 不要过拟合

## 快捷命令

- push 表示执行提交git 并执行push，不用你管pull的事
