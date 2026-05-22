# Just Saying Desktop V1

Just Saying 是一个桌面浮窗工具：先在目标对话框里输入口语化文字，再点浮窗里的 `优化`，它会原地把当前输入框内容改写成更清楚的 prompt。

语音转文字交给系统输入法或豆包输入法；Just Saying 只负责清洗、整理和强化 prompt。

## 运行

```bash
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

启动后会出现一个很小的置顶毛玻璃浮窗，主按钮是 `优化`，旁边有 `撤`、`...` 和 `-`。

## 模型设置

点击浮窗里的 `...`：

1. 选择 provider。
2. 粘贴 API key；如果 `Cmd+V` 没反应，点 API Key 右侧的 `粘贴`。
3. 点 `寻找模型`。
4. 从搜索结果里选择模型，或手动填写模型 ID。
5. 按需要修改优化快捷键和还原快捷键。
6. 按需要修改优化提示词。
7. 点 `保存`。

设置会保存到项目根目录的 `.env`。`.env` 不要提交；它包含 API key、Base URL、模型 ID、provider 和自定义优化提示词。

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
5. 点击 `-` 可以把浮窗缩小，再点 `+` 展开。
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
JUSTSAYING_OPTIMIZE_PROMPT=你是一个语音提示词清洗助手。\n输出只包含整理后的 prompt，不要解释。
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

- macOS 需要给运行 `python -m app.main` 的终端或 Python 授予 Accessibility 权限，否则无法自动 `Cmd+A/C/V`。
- 默认 `Option + Shift` 是优化快捷键，默认连续三下 `Option` 是还原快捷键。
- 快捷键可在设置窗口修改，支持格式如 `option+shift`、`option+space`、`command+z`、`option*3`。
- 浮窗会记住最后一个非 Just Saying 的前台 App。
- 当前版本优先使用 Accessibility 直接读写焦点文本元素；如果目标 App 不暴露可写文本值，则退回快捷键方式。
- 目标 App 需要能在重新激活后保留输入框焦点；如果网页或 App 特殊处理焦点，仍可能读不到文字。
- 只恢复文本剪贴板内容；如果原剪贴板是图片或富文本，当前版本不会完整还原。
- prompt 内容和语音内容不会落盘；API key 只保存到你本机项目目录里的 `.env`。
