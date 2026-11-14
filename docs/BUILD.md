# 构建与验收

使用 Windows 10/11 x64、Python 3.12 x64。先把 FFmpeg/FFprobe 放在 PATH，或用 `-FFmpegDirectory` 指定其所在文件夹：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

首次构建会安装开发依赖与 Playwright Chromium，准备第三方许可需联网。已有浏览器缓存时可传 `-ChromiumSource`，要求该目录下有 `chrome-win64/chrome.exe`。不要把不同版本混进同一 resources/chromium-custom 目录。

产物为 `dist/网络ASR/` 和 `release/NetworkASR-v1.2.0-windows-x64.zip`，同时生成 SHA256SUMS.txt。源码仓库不提交这些大文件，ZIP 通过 GitHub Release 分发。

PyInstaller 打包时带入 Qt WebEngine、Qt 插件、VC 运行库、Python 解释器、FFmpeg/FFprobe 与解析浏览器。UI 强制使用 Qt 后端，不回退到依赖系统安装的 WebView2。Qt 和解析浏览器是不同用途的两个运行时。原生窗口支持和范围参考 [Qt 6.8 平台表](https://doc.qt.io/qt-6.8/supported-platforms.html)。

构建脚本会运行 `verify_portable.py`：移除 Python/Qt 环境设置、PATH 仅留 System32、在中文及空格临时工作目录启动 exe，并检查 HTML、原生桥、图标、导航、FFmpeg、FFprobe、实际音频提取和解析浏览器。全过程不调用 ASR，不消耗额度，数据使用隔离临时目录。

这能检查运行包是否偷偷依赖开发机的 PATH，不能替代所有 Windows 驱动、杀毒策略和硬件组合的验收。当前机器没有 Windows Sandbox，未把本机检查写成“所有 Windows 测试通过”。发布前的检查结果放在 release/VERIFICATION.md 和包内 diagnostics.json 中。

## 发布

仓库配置了 Windows 构建流程。推送 v 开头的标签后，工作流会在 Windows runner 上构建并验证完整包，再上传 Release ZIP 和校验文件。首次发布也可以使用 GitHub MCP 创建 Release，并上传本地已验证的相同产物。

不要上传 .env、config.json、history.db、日志、缓存、用户素材或真实密钥。README 的 REPOSITORY_URL 在首次创建仓库后替换为实际地址；生成发布包时 README 也会随包复制。
