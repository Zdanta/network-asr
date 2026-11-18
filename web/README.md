# 网络ASR Web

本目录为 FastAPI + React Web 项目。仓库根目录继续保留 Windows 桌面项目；Web 发布使用 web-* 标签。

## 本次版本

web-v2026.11.19.1 修正抖音导入误选整页媒体的缺陷：分享页与浏览器都只使用目标视频编号匹配的结构化 video 数据。无法验证则导入失败，在创建 ASR 任务前停止，不调用 ASR、不扣费。配套音频限定同一视频。

当前实际问题链接没有返回目标视频数据，尚未验证该链接可恢复成功下载。平台风控、私密、失效或无目标数据时仍可能失败。

## 目录与运行

- ai-video-api：Python 3.12、FastAPI、SQLAlchemy/MySQL、HTTPX、FFmpeg、Playwright。
- ai-video-web-react：React、TypeScript、Vite、TanStack Query、Zustand。
- scripts/package_release.py：生成 Web 源码/构建产物部署包及 SHA256。

后端：在 ai-video-api 建立虚拟环境，pip install -r requirements.txt，复制 .env.example 为 .env 并配置 MySQL、认证签名密钥、ASR、邮件与支付参数，安装 FFmpeg/FFprobe 与 Chromium（或 python -m playwright install chromium），运行 uvicorn app.main:app --host 127.0.0.1 --port 8000。

前端：Node.js 22，进入 ai-video-web-react，npm ci、npm run dev。正式构建为 npm run build，dist 可交由 Nginx 托管。

Docker：在本目录复制 .env.example 为 .env 并配置生产参数，使用 docker compose -p ai-video -f docker-compose.prod.yml build，然后 up -d。示例 Compose 仅提供业务服务，MySQL 需另行配置。已有生产环境升级时保留原 Compose、HTTPS/反向代理、环境文件及存储挂载，先备份再切换；不要用示例配置覆盖生产。

数据库增量脚本位于 ai-video-api/scripts。本次下载修复无需 migration。此前邮箱、支付与访客功能所需迁移应按现有库版本逐项核对；此发布不承诺直接初始化一个空库。

## 配置与验证

API Key 仅放服务端，opcpay 使用 opcpay_api_key。模板没有真实凭据。不要提交 .env、用户媒体、日志或数据库备份。

后端：python -m unittest discover -s tests（在 ai-video-api 执行）。本地 81 项：71 通过，10 项专用数据库测试跳过。媒体下载 13 项全通过。前端 npm run build、npm run lint 通过。测试不执行真实支付、ASR 或 SMTP 发信。

发布包含源码、环境模板及前端 dist；不是 Windows 便携 EXE，也不含 Python/Node/Docker 镜像、MySQL、媒体文件或凭据。依赖版本以 requirements.txt 和 package-lock.json 为准。
