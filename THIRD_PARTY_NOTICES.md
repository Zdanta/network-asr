# 第三方组件

网络ASR的应用源码采用 MIT 许可证，第三方组件不因此改变许可。发行包将保留 notices 目录、组件版本、许可文本以及 FFmpeg 构建参数。

| 组件 | 用途 | 许可 / 源码 |
| --- | --- | --- |
| Python | 应用运行时 | [PSF](https://www.python.org/psf/license/) / https://www.python.org/downloads/source/ |
| pywebview | Python 与本地 HTML 桥接 | BSD-3-Clause / https://github.com/r0x0r/pywebview |
| PySide6、Qt 6.8.3 | 原生窗口、Qt WebEngine | LGPL-3.0 等 / https://download.qt.io/official_releases/qt/6.8/6.8.3/submodules/ 与 https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.8.3 |
| QtPy | Qt 绑定兼容层 | MIT / https://github.com/spyder-ide/qtpy |
| Playwright | 抖音分享页解析 | Apache-2.0 / https://github.com/microsoft/playwright-python |
| Chromium / Chrome for Testing | 解析浏览器及 Qt WebEngine 的网页引擎 | BSD 等多种许可；浏览器的 chrome://credits 提供完整归属 / https://chromium.googlesource.com/chromium/src/ |
| FFmpeg、FFprobe | 音视频探测与提取 | 本次 Gyan 8.1 static full 构建启用 GPLv3；主源码随包附在 notices/sources，构建信息在 notices/FFmpeg-build.txt / https://ffmpeg.org/ 与 https://www.gyan.dev/ffmpeg/builds/ |
| HTTPX 及依赖 | HTTPS 调用 | BSD、MIT、MPL 等，见随包 notices |

Qt 动态库以独立文件提供，不禁止用户修改或替换这些库；替换时需保持 ABI 和版本兼容。FFmpeg 通过独立进程调用。FFmpeg 包含的第三方编解码库及构建脚本可在构建提供方页面及对应上游项目查询，不将其归为本项目原创。

重新分发或自行更换二进制时，请保留对应版本的许可、版权及源码获取信息。发布包没有对第三方组件增加禁止修改或逆向工程的条款。
