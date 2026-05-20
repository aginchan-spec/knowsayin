# justsaying

A voice-input prompt cleaner for turning spoken thinking-flow text into concise, usable AI prompts.

## Product Idea

Voice input often includes filler words, repeated phrases, false starts, and self-corrections. justsaying sits between speech-to-text and an AI model, helping turn raw transcript text into a clearer prompt before sending.

Core principle:

```text
Clean expression, do not change intent.
Organize structure, do not silently decide for the user.
```

## Initial Modes

- **Clean**: remove obvious filler and repetition while preserving phrasing.
- **Organize**: rewrite the transcript into a concise, clear request.
- **Strengthen**: turn the intent into a structured prompt with task, context, constraints, and output format.

## Privacy

Treat transcripts as private by default. Do not commit raw private recordings, private transcripts, API keys, tokens, or credentials.

## Project Memory

Before work, read `AGENTS.md`, then `MemoryBank/projects/justsaying.md`.
