# AI辅助信息

## SSH

主机名：局域网 mini 或者 (57c42474b0ea.ofalias.net 端口 58186)
用户名 leo
密码 见.env 里的 SSH_PASSWORD

StableDiffusion 目录 /mnt/data/stable-diffusion/webui
sd日志查询 journalctl -u sd.service -f

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

## 软件环境

python相关调用使用 **conda**，env: flask_env

## 注意

- 重跑任务需要我明确提出了才进行，如果你想重跑需要我二次确认
- 创建的临时文件记得删除
- 重启服务要找我确认
- 变量定义注意拼写，避免cSpell告警
