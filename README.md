# ArXiv Assistant

A personal AI research briefing. Every weekday at 07:00 it scans new arXiv papers across
AI, robotics, quantum and deep tech, picks the 7 most worth reading, and explains each one
on Telegram in plain English. Every Sunday at 09:00 it sends the top 5 of the week with a
"big picture" of the trends. Everything is also published to a website.

**Website:** https://camillelebihan.github.io/ArXiv-Assistant

## What a card looks like

```
🦾 Humanoid robot learns household manipulation from video
Ada L., Bo C. et al. · Robotics & embodied AI

• In short: Shows a robot can learn chores from ordinary videos.
• Picture it: Like an apprentice learning by watching a chef.
• Key term: Imitation learning: learning a skill by copying demonstrations.
• Why it matters: Home and warehouse robots could be trained far more cheaply.
• Future signal: Online video is becoming robotics' training data.
• Ask an expert: How much real-world robot data do you still need?

Novelty  ●●●●○   Rigor    ●●●○○
Impact   ●●●●○   For you  ●●●●●      Overall 4.0/5
```

## How it works

1. **Fetch:** pages through the newest arXiv papers in the categories listed in `topics.toml`.
2. **Pre-select:** keeps papers matching your themes' keywords (cheap, no AI).
3. **Score:** Gemini rates the best ~60 on four axes: novelty, rigor, real-world impact and
   relevance to your profile. Theme weights keep some topics occasional (e.g. finance).
4. **Pick:** best overall first, at most 2 papers per theme, so you get breadth.
5. **Explain:** Gemini writes each card; Telegram gets one message per paper.
6. **Publish:** state is saved as JSON and the website is rebuilt.

Scores are Gemini's first impression from the abstract, not a peer review.

## Make it yours

Edit **`topics.toml`**: your profile, the arXiv categories, each theme's keywords and weight,
and the scoring weights. No code changes needed.

## Run it

### Always on (GitHub Actions, recommended)
The workflow `.github/workflows/digest.yml` builds the Docker image and runs it on GitHub's
servers several times each morning; the bot sends only what is due, so it is robust to delays
and daylight-saving time. State lives on the `data` branch.

1. Repo **Settings → Secrets and variables → Actions → New repository secret**:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`.
2. Repo **Settings → Pages → Source: GitHub Actions**.
3. **Actions → Digest → Run workflow → `check`** to test, then `daily` for a first digest.

Optional: a repository *variable* `GEMINI_MODEL` changes the model (default `gemini-2.5-flash`).

### Locally (Docker)
```bash
cp .env.example .env                                   # fill in the three keys
docker compose run --rm bot python -m src.main check   # test Gemini + Telegram
docker compose run --rm bot python -m src.main daily   # send a digest now
docker compose run --rm bot python -m src.main site /data/site   # build the website
```
Don't run the local loop and GitHub Actions at the same time, or you'll get everything twice.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q && ruff check .
```

Pull requests are reviewed by [Gemini Code Assist](https://github.com/apps/gemini-code-assist)
(settings in `.gemini/`); CI runs lint, tests and a Docker build.

```
topics.toml        your themes, profile and scoring weights
src/
├── arxiv_client.py  fetch, tag themes, pre-select
├── llm.py           Gemini calls: JSON, spacing, retries, visible errors
├── ranker.py        four-axis scoring and diverse selection
├── summarizer.py    cards and the weekly big picture
├── telegram.py      message formatting and sending
├── state.py         JSON state (sent papers, daily and weekly digests)
├── site.py          static website (+ style.css)
└── main.py          commands: check, daily, weekly, auto, site, loop
```

## Roadmap

- [ ] `/search <topic>` command for on-demand briefings
- [ ] Rank with embeddings against papers you liked
- [ ] Add non-arXiv sources (lab blogs, funding news)
