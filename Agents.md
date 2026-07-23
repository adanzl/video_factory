# AI辅助信息

## SSH

主机名：

- 局域网 主机: mini  
- 广域网 主机：vip.bj.frp.one:19367
- 广域网 主机：57c42474b0ea.ofalias.net:58186
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

## 注意

- 重跑任务需要我明确提出了才进行，如果你想重跑需要我二次确认
- 创建的临时文件记得删除
- 重启服务要找我确认
- 变量定义注意拼写，避免cSpell告警
- 新建独立文件要找我二次确认，没必要不要做
- 使用Tailwind
- 我让你查数据 先从远程服务器上查
- 给出的回答要有根据，别瞎猜
- 除非特殊说明，日志和数据都去查远程的
- 你要是说服务器就旧代码先去服务器上查git记录再说
- 不要用powershell命令执行远程查询
- 要测试先本地测通过了再推送，除非我要求，不要远程测试

## 快捷命令

- push 表示执行提交git 并执行push
