# KnowSayin

KnowSayin turns rough dictated notes, stream-of-consciousness text, or messy first drafts into clearer prompts.

It is a macOS desktop helper plus a lightweight web cleaner at [knowsayin.com](https://knowsayin.com). The app uses the hosted KnowSayin service; users do not need to deploy a server, choose a model provider, or bring an API key.

## Download

Early macOS builds are installed from this repository:

```bash
git clone https://github.com/aginchan-spec/knowsayin.git
cd knowsayin
scripts/install_macos.sh
open "/Applications/KnowSayin.app"
```

This installs the desktop client only. Optimization still runs through KnowSayin Cloud.

On first launch, enable macOS Accessibility permission for `KnowSayin.app`:

```text
System Settings -> Privacy & Security -> Accessibility
```

Without Accessibility permission, the app can open, but it cannot read or replace text in the active input field.

## How It Works

1. Type or dictate rough text into ChatGPT, Claude, a browser, a note app, or another text field.
2. Click `Optimize` in the small floating window, or press `Option + Shift`.
3. KnowSayin replaces the current text with a cleaner prompt.
4. Click `Undo`, or press `Option` three times, to restore the previous text.
5. If the floating window is hidden, restore it from the macOS menu bar item `KS -> Show Floating Window`.

Free quota starts at 20 uses and refills automatically. When quota is empty, `Optimize` changes to `Get extra`; it opens the KnowSayin website with the machine code already included. Choose a nice note for the author, submit it, and the quota refills for free.

## Web Cleaner

The website at [knowsayin.com](https://knowsayin.com) can also clean prompts directly in the browser. Paste text, optimize it, then copy the result.

The page automatically follows the browser/system language for English or Chinese interface text.

## Privacy

- The desktop client does not store raw prompt text, voice recordings, or private transcripts.
- KnowSayin Cloud processes submitted text only to return the cleaned prompt.
- Usage accounting is based on quota and character counts, not saved prompt contents.
- The desktop client does not include provider API keys.
- Never commit `.env`, private recordings, private transcripts, API keys, tokens, or credentials.

## Local Client Development

For contributors working on the macOS client:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
python -m app.main
```

Build and install the macOS app locally:

```bash
scripts/build_macos_app.sh
open "/Applications/KnowSayin.app"
```

The bundle id is `com.knowsayin.app`. Local ad-hoc builds may need Accessibility permission again after rebuilding. Public release builds should use a stable Developer ID signature and notarization.

## Notes For Contributors

- The supported user setup is the official hosted KnowSayin service.
- Self-hosting is not a public user workflow and is not documented here.
- Production infrastructure, deployment units, machine names, internal paths, private environment files, and service secrets are intentionally kept out of the public repository.
- The active desktop configuration is fixed to `KnowSayin Cloud`; users should not be asked to configure their own API provider, base URL, model ID, or API key.

## Requirements And Limits

- macOS is currently required for the desktop client.
- The active target app must keep focus in the input field when KnowSayin switches back to it.
- If an app blocks direct text replacement, KnowSayin falls back to clipboard-based replacement where possible.
- Only text clipboard contents are restored after replacement; images or rich clipboard data may not be fully restored.
