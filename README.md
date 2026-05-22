# KnowSayin Desktop V1

KnowSayin 是一个桌面浮窗工具：先在目标对话框里输入口语化文字，再点浮窗里的 `优化`，它会原地把当前输入框内容改写成更清楚的 prompt。

语音转文字交给系统输入法或豆包输入法；KnowSayin 只负责清洗、整理和强化 prompt。

## 默认云服务

默认 provider 是 `KnowSayin Cloud`，客户端固定连接：

```text
https://api.knowsayin.com
```

不要把 VM101、AWS EC2、内网 host、临时 tunnel 或机器 IP 写进客户端配置。以后从 VM101 迁移到 EC2 时，只切换 Cloudflare DNS/反代，已安装软件仍然请求同一个 `api.knowsayin.com`。

KnowSayin Cloud API 使用版本化路径：

```text
GET  /v1/health
GET  /v1/config
POST /v1/session
POST /v1/usage
POST /v1/clean
```

客户端不会携带 DeepSeek API key。DeepSeek key 只放在服务器环境变量里。

## 从 GitHub 安装 macOS 桌面版

如果 repo 还是 private，先确认本机 GitHub 已登录并有访问权限；公开发布给用户前，建议把安装仓库改成 public，或提供下载包。

```bash
git clone https://github.com/aginchan-spec/knowsayin.git
cd knowsayin
python3 -m pip install --user -r requirements.txt
cp .env.example .env
scripts/build_macos_app.sh
open "/Applications/KnowSayin.app"
```

首次打开后，到 macOS：

```text
System Settings -> Privacy & Security -> Accessibility
```

给 `KnowSayin.app` 打开权限。没有 Accessibility 权限时，App 可以启动，但无法读取和替换目标输入框文字。

## 运行桌面版开发模式

```bash
python3 -m pip install --user -r requirements.txt
cp .env.example .env
python -m app.main
```

启动后会出现一个很小的置顶毛玻璃浮窗，主按钮是 `优化`，旁边有 `撤`、`...` 和 `-`。菜单栏也会出现 `KS`，用于显示浮窗、打开设置、检查更新、打开授权设置或退出。

打包成双击启动的 macOS App：

```bash
scripts/build_macos_app.sh
open "/Applications/KnowSayin.app"
```

打包脚本固定使用 bundle id `com.knowsayin.app`。打包版读取 `~/Library/Application Support/KnowSayin/.env`；如果这个文件不存在，会从项目 `.env` 初始化一次。

## 运行 VM101/API 中转服务

在服务器环境文件中配置真实密钥，不要写入 repo：

```bash
KNOWSAYIN_API_ALLOWED_ORIGINS=https://knowsayin.com
KNOWSAYIN_API_TOKEN_SECRET=replace-with-random-server-secret
KNOWSAYIN_UPSTREAM_BASE_URL=https://api.deepseek.com/v1
KNOWSAYIN_UPSTREAM_MODEL=deepseek-chat
KNOWSAYIN_UPSTREAM_API_KEY=
```

本地或服务器启动：

```bash
python -m app.cloud_api --host 127.0.0.1 --port 8788
```

生产环境由 Cloudflare/反代把 `https://api.knowsayin.com` 转发到这个服务。迁移到 AWS EC2 时，在 EC2 部署同版本服务并切换 `api.knowsayin.com`，旧客户端无需更新。

## 手机网页

手机网页用于轻量试用：打开网页，输入或粘贴文字，点击 `优化`，再复制结果到别处；需要重来时点 `清除`。输入框会显示字数，较长文本会自动用长文本整理提示词。

本地运行：

```bash
python -m app.web --host 127.0.0.1 --port 8787
```

生成朋友专属链接配置：

```bash
python -m app.web --make-pass Anna --daily-limit 100 --max-chars 3000 --base-url https://knowsayin.com
```

使用记录只保存每日次数和字符数，不保存原文和优化结果。

## 模型设置

点击浮窗里的 `...`：

1. 默认选择 `KnowSayin Cloud`，不需要填写本机 API key。
2. 如果要自备 provider，可切换到 OpenAI、DeepSeek、OpenRouter 等兼容 OpenAI API 的服务。
3. 按需要修改优化快捷键和还原快捷键。
4. 按需要修改优化提示词。
5. 点 `保存`。

如果云服务不可用、额度耗尽或上游失败，桌面版不会用低质量 fallback 静默替换原文；它会显示错误并保留用户输入。只有在用户主动选择自备 provider 且未配置 key 时，才使用本地基础清洗。

## 使用流程

1. 在 ChatGPT、Claude、浏览器、微信或其他目标输入框里输入一段文字。
2. 点击 KnowSayin 浮窗里的 `优化`，或按 `Option + Shift`。
3. KnowSayin 会切回目标 App，优先用 macOS Accessibility 直接读取和替换当前文本；不支持时再退回 `Cmd+A/C/V`。
4. 如果想撤回最近一次优化，点击 `撤`，或连续按三下 `Option`。
5. 点击 `-` 会隐藏浮窗；需要恢复时，从 macOS 菜单栏 `KS` 里点 `显示浮窗`。

## 配置示例

```bash
KNOWSAYIN_PROVIDER=knowsayin
KNOWSAYIN_CLOUD_BASE_URL=https://api.knowsayin.com
KNOWSAYIN_CLOUD_MODEL=knowsayin-cloud
KNOWSAYIN_OPTIMIZE_HOTKEY=option+shift
KNOWSAYIN_UNDO_HOTKEY=option*3
```

自备 provider：

```bash
KNOWSAYIN_PROVIDER=deepseek
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

## 权限和限制

- macOS 需要给 `KnowSayin.app`、或运行 `python -m app.main` 的终端/Python 授予 Accessibility 权限，否则无法读取和替换当前输入框文字。
- bundle id 是 `com.knowsayin.app`。重新打包或迁移机器后，macOS 可能要求重新授权一次。
- 默认 `Option + Shift` 和三下 `Option` 不需要额外 Input Monitoring。
- 目标 App 需要能在重新激活后保留输入框焦点；如果网页或 App 特殊处理焦点，仍可能读不到文字。
- 只恢复文本剪贴板内容；如果原剪贴板是图片或富文本，当前版本不会完整还原。
- prompt 内容和语音内容不会落盘；云 API 日志也不保存原文或优化结果。
