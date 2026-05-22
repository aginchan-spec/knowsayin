# Just Saying Desktop V1

Just Saying 是一个桌面浮窗工具：先在目标对话框里输入口语化文字，再点浮窗里的 `优化`，它会原地把当前输入框内容改写成更清楚的 prompt。

语音转文字交给系统输入法或豆包输入法；Just Saying 只负责清洗、整理和强化 prompt。

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

启动后会出现一个很小的置顶毛玻璃浮窗，主按钮是 `优化`，旁边有 `撤`、`...` 和 `-`。菜单栏也会出现 `JS`，用于显示浮窗、打开设置、打开授权设置或退出。

打包成双击启动的 macOS App：

```bash
scripts/build_macos_app.sh
open "/Applications/Just Saying.app"
```

macOS 权限会绑定到打包后的 App 身份。打包脚本固定使用 bundle id `com.chris.justsaying`，避免每次构建后系统设置里出现看似已授权、实际不匹配的旧授权项。

打包版会读取 `~/Library/Application Support/Just Saying/.env`。如果这个文件还不存在，打包脚本会从项目目录复制本机 `.env` 过去一次；后续在设置窗口保存，也会写入这个位置。这样双击启动时不需要额外申请 Documents 文件夹权限。

## 手机网页

手机网页用于给朋友免费试用：打开网页，输入或粘贴文字，点击 `优化`，再复制结果到别处；需要重来时点 `清除`。输入框会显示字数，较长文本会自动用长文本整理提示词，完成后页面会跳到结果区。浏览器不会拿到 DeepSeek API key；网页只请求本机/服务器上的 `app.web`，由后端读取 `.env` 调用模型。

本地运行：

```bash
python -m app.web --host 127.0.0.1 --port 8787
```

生成朋友专属链接配置：

```bash
python -m app.web --make-pass Anna --daily-limit 100 --max-chars 3000 --base-url https://mehelper.com/justsaying
```

把输出的 `JUSTSAYING_WEB_PASSES='...'` 放进服务器 `.env`。朋友使用输出的 `/p/<pass>` 链接打开后，浏览器会保存 pass，以后直接打开主页也能继续用。

网页限额配置示例：

```bash
JUSTSAYING_WEB_SITE_URL=https://mehelper.com/justsaying
JUSTSAYING_WEB_BASE_PATH=/justsaying
JUSTSAYING_WEB_REQUIRE_PASS=true
JUSTSAYING_WEB_DEFAULT_DAILY_LIMIT=100
JUSTSAYING_WEB_DEFAULT_MAX_CHARS=3000
JUSTSAYING_WEB_GLOBAL_DAILY_LIMIT=1000
JUSTSAYING_WEB_PASSES=anna:随机口令:100:3000:true,ben:另一个随机口令:50:3000:true
```

使用记录只保存每日次数和字符数，不保存原文和优化结果。

## 模型设置

点击浮窗里的 `...`：

1. 选择 provider。
2. 粘贴 API key；如果 `Cmd+V` 没反应，点 API Key 右侧的 `粘贴`。
3. 点 `寻找模型`。
4. 从搜索结果里选择模型，或手动填写模型 ID。
5. 按需要修改优化快捷键和还原快捷键。
6. 按需要修改优化提示词。
7. 点 `保存`。

开发模式下，设置会保存到项目根目录的 `.env`。打包版 App 会保存到 `~/Library/Application Support/Just Saying/.env`。`.env` 不要提交；它包含 API key、Base URL、模型 ID、provider 和自定义优化提示词。

当前内置 OpenAI-compatible provider 预设：

- OpenAI
- OpenRouter
- DeepSeek
- Groq
- Mistral
- Together AI
- xAI
- Moonshot
- Qwen / DashScope
- Doubao / Volcano Ark
- Custom OpenAI-compatible

## 使用流程

1. 在 ChatGPT、Claude、浏览器、微信或其他目标输入框里输入一段文字。
2. 如果想整理，点击 Just Saying 浮窗里的 `优化`，或按 `Option + Shift`。
3. Just Saying 会切回你刚才使用的目标 App，优先用 macOS Accessibility 直接读取和替换当前文本；不支持时再退回 `Cmd+A/C/V`。
4. 如果想撤回最近一次优化，点击 `撤`，或连续按三下 `Option`。
5. 点击 `-` 会完全隐藏浮窗；需要恢复时，从 macOS 菜单栏 `JS` 里点 `显示浮窗`。
6. 确认没问题后，在原应用里正常提交。

## 配置

推荐使用浮窗里的设置窗口写入 `.env`。也可以手动编辑：

```bash
JUSTSAYING_PROVIDER=openai
OPENAI_API_KEY=你的 key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-nano
JUSTSAYING_OPTIMIZE_HOTKEY=option+shift
JUSTSAYING_UNDO_HOTKEY=option*3
```

兼容 OpenAI API 的服务可以改 `OPENAI_BASE_URL`，例如：

```bash
OPENAI_BASE_URL=https://example.com/v1
```

自定义优化提示词也会写入 `.env`：

```bash
JUSTSAYING_OPTIMIZE_PROMPT=You are a voice-to-prompt cleanup assistant.\nRewrite the user's rough spoken text into a clear AI prompt.\nOutput only the cleaned prompt. Do not explain your changes.
```

如果没有配置 API key，会使用本地 fallback 清洗逻辑，方便先跑通流程。

## 文件结构

```text
app/
  __init__.py
  config.py
  main.py
  model_config.py
  optimizer.py
  paste.py
.env.example
.gitignore
requirements.txt
README.md
```

## 权限和限制

- macOS 需要给 `Just Saying.app`、或运行 `python -m app.main` 的终端/Python 授予 Accessibility 权限，否则无法读取和替换当前输入框文字。
- 如果授权没做好，Just Saying 会提示你；点菜单栏 `JS` -> `打开授权设置`，然后在 Accessibility 里允许 Just Saying。
- 如果刚重新打包过 App，授权开关看起来已经打开但仍提示授权，请把旧的 Just Saying 权限移除或重新开关一次，然后完全退出并重新打开 `/Applications/Just Saying.app`。
- 默认 `Option + Shift` 和三下 `Option` 不需要额外 Input Monitoring。只有把快捷键改成 `option+return`、`command+z` 这类带普通按键的组合时，才可能需要在 Input Monitoring 里允许 Just Saying。
- macOS 不允许 App 自动替用户勾选权限；第一次安装仍需要用户在系统设置里手动打开开关。
- 默认 `Option + Shift` 是优化快捷键，默认连续三下 `Option` 是还原快捷键。
- 快捷键可在设置窗口修改，支持格式如 `option+shift`、`option+space`、`command+z`、`option*3`。
- 浮窗会记住最后一个非 Just Saying 的前台 App。
- 当前版本优先使用 Accessibility 直接读写焦点文本元素；如果目标 App 不暴露可写文本值，则退回快捷键方式。
- 目标 App 需要能在重新激活后保留输入框焦点；如果网页或 App 特殊处理焦点，仍可能读不到文字。
- 只恢复文本剪贴板内容；如果原剪贴板是图片或富文本，当前版本不会完整还原。
- prompt 内容和语音内容不会落盘；API key 只保存到你本机项目目录里的 `.env`。
