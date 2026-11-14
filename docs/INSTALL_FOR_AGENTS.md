# 帮用户安装网络ASR

优先下载当前仓库最新稳定 Release 的 `NetworkASR-*-windows-x64.zip`，不要给普通用户安装 Python 或从源码构建。

1. 确认 Windows 10/11 x64（Qt 6.8 的 Windows 10 最低版本为 1809）。不支持 Windows 7、32 位 Windows 或原生 ARM64 发布包。
2. 阅读 Release 说明，下载便携 ZIP 和 SHA256SUMS.txt，校验下载的 ZIP 哈希。
3. 将完整目录解压到当前用户可写目录，例如 `%LOCALAPPDATA%/Programs/NetworkASR`；遇到旧版本时先保留旧文件夹，再解压到新目录，不要覆盖运行中的程序。
4. 可按用户要求创建桌面快捷方式，目标为解压目录下的 `网络ASR.exe`，工作目录设为同一目录。
5. 启动应用，提示用户在设置页填写自己的火山豆包语音 API Key。不要索取、输出或从别的项目复制密钥。
6. 不要自动提交收费 ASR 任务。使用程序 `--smoke-test <绝对JSON路径>` 可以做不联网识别、不收费的运行时诊断；诊断使用临时数据目录。

配置和任务历史在 `%LOCALAPPDATA%/AiVideoDesktop`，升级时不要删除。完整包已携带 Qt WebEngine 和 VC 运行库，不需要 WebView2 引导安装器、系统 Python、Node 或独立 FFmpeg。
