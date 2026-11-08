# Review style guide

- Python 3.12, type hints on every public function.
- Network calls (arXiv, Gemini, Telegram) must have a timeout and must not crash the daily scheduler.
- Never log or commit secrets (tokens, API keys).
- Telegram messages use HTML parse mode: all user/paper text must be escaped.
- Every new function needs a unit test that runs without network access.
- Keep modules small and single-purpose: fetching, summarizing, sending and storage stay separate.
