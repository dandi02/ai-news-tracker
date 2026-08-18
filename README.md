# SQP AI News Tracker

Automated daily tracker for **open-source LLM news**. Every day it scans GitHub,
Hugging Face, Reddit, Hacker News, blogs, arXiv, YouTube, and Bluesky, has Claude
curate and score what it finds, and publishes a feed for the whole team.

## 🔗 Live deployment

| Page | URL |
|---|---|
| 🌐 **News feed** (share this) | **https://dandi02.github.io/ai-news-tracker/** |
| 📡 RSS feed (for feed readers) | https://dandi02.github.io/ai-news-tracker/feed.xml |
| ⚙️ Admin console + link hub | https://dandi02.github.io/ai-news-tracker/admin.html |
| 🏗️ Daily build runs & logs | https://github.com/dandi02/ai-news-tracker/actions |

**Status**: fully operational — daily automatic runs at 11:47 UTC (ready by
~6 AM Pacific), Claude AI
curation enabled, GitHub leaderboards + watchlist live. To change what gets
tracked, edit [config/sources.yaml](config/sources.yaml) (or use the admin
console) — the next run picks it up.

Everything runs on GitHub Actions — no servers, no database. State lives in JSON
files committed to this repo. AI curation costs roughly **$0.10/day** (Claude
Haiku 4.5); if the API is ever unavailable, a keyword-scoring fallback keeps the
feed shipping (items get a "keyword-ranked" badge).

---

## One-time setup (~10 minutes) — ✅ already done for this deployment

*Kept for reference, or for forking this tracker to another repo/team.*

1. **Create the GitHub repository** and push this code:

   ```sh
   git remote add origin git@github.com:YOUR_ORG/ai-news-tracker.git
   git push -u origin main
   ```

   > GitHub Pages on the free plan requires a **public** repo (private repos need
   > GitHub Pro/Team).

2. **Add the Claude API key**: repo → *Settings → Secrets and variables → Actions →
   New repository secret* → name `ANTHROPIC_API_KEY`, value from
   [platform.claude.com](https://platform.claude.com/).

3. **Enable Pages**: repo → *Settings → Pages → Source:* **GitHub Actions**.

4. **First run**: *Actions* tab → "Daily build" → *Run workflow*. When it goes
   green, the feed is live at `https://YOUR_ORG.github.io/ai-news-tracker/`.

5. Share the URL with the team. The RSS feed is at `…/feed.xml`. The pipeline
   then runs automatically every day at 05:17 UTC (edit the cron in
   [.github/workflows/build.yml](.github/workflows/build.yml) to taste).

### Admin access (optional, for source management & curation)

The admin console needs a **fine-grained personal access token**:

1. GitHub → *Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token*.
2. Resource owner: your org. Repository access: **Only select repositories** →
   this repo. Permissions: **Contents: Read and write**, **Actions: Read and
   write**. Expiry: 90 days recommended.
3. Open `…/admin.html`, paste the token once (it stays in that browser's
   localStorage). Anyone holding the token can write to this repo — only use it
   on trusted machines, and use "Forget token" on shared ones.

From the console admins can add/remove/disable **subreddits, GitHub release
watchlist repos, RSS feeds, YouTube channels, and Bluesky handles**, and
**pin / hide / tag** feed items. Every change is a commit (full audit trail).
"Re-scan now" triggers the pipeline immediately.

---

## How it works

```
sources.yaml ──► fetchers (8) ──► dedupe ──► prefilter ──► Claude curation ──► overrides ──► render
                 GitHub API/atom     seen.json   keywords +      keep/drop        pin/hide/tag   feed.json
                 HF API, reddit,     cross-src   engagement,     summary,                        feed.xml
                 HN Algolia, RSS,    merge       cap ~150        importance 1-10,                day archive
                 YouTube, Bluesky                                category, groups
```

- **Curation** (`pipeline/curator.py`): batched calls to `claude-haiku-4-5` with a
  strict JSON schema (structured outputs). Claude drops noise, writes factual
  1–2 sentence summaries, scores importance (major open-weights release = 9–10,
  single fine-tune = 2–4), and assigns `group_key`s so the same story reported by
  Reddit + HN + a blog collapses into one card with "also on …" links.
- **State** (`data/`): `seen.json` prevents re-curation (120-day retention),
  `days/*.json` is the durable per-day archive, `overrides.json` holds admin
  curation. The workflow commits state back after each run; it never triggers on
  push, so there is no loop.
- **Site** (`site/`): static HTML/JS, no build step. Filters by category, source,
  importance, and text; pinned section; dark/light theme; failure warnings.

## Local development

```sh
pip install -r requirements.txt
python -m pytest                                  # unit tests, no network
python -m pipeline.run --dry-run --no-llm --limit 10   # fetch live, write to build-preview/
python -m pipeline.run --no-llm                   # full run, keyword scoring
ANTHROPIC_API_KEY=sk-… python -m pipeline.run     # full run with Claude curation
python -m http.server 8000 --directory site       # preview at localhost:8000
```

`--dry-run` writes to `build-preview/` and leaves state untouched. `--no-llm`
forces the keyword fallback. `--limit N` caps items per source for fast runs.

## Known limitations & failure modes

- **X/Twitter is not tracked** — there is no free read API and scraping violates
  ToS. Influencers are followed via their Bluesky handles, YouTube channels, and
  blogs instead (all admin-configurable).
- **Reddit** sometimes 403-blocks cloud IPs on its JSON endpoints; the fetcher
  automatically falls back to the RSS endpoints. If both fail, the run continues
  without Reddit and the site shows a source-failure warning.
- **YouTube feeds** are intermittently rate-limited from some networks; failures
  are per-channel and non-fatal.
- **GitHub search** has strict secondary rate limits — the fetcher keeps to ≤4
  authenticated queries. Release tracking uses public `releases.atom` feeds,
  which have no quota at all.
- **arXiv cs.CL** lists 100–200 papers/day; entries are keyword-gated and capped
  at 20 before curation. Its feed is empty on weekends — that is not a failure.
- **Scheduled workflows** can lag several minutes under GitHub load, and GitHub
  disables schedules after 60 days without repo activity (the daily state commit
  keeps the repo active).
- **Claude API failure** → keyword fallback scoring; the feed still updates and
  affected items show a "keyword-ranked" badge.
- If **every** source fails, the previous feed is left untouched and the run
  exits nonzero so Actions notifies watchers.

## Cost

| Component | Cost |
|---|---|
| GitHub Actions (~3 min/day) | free tier |
| GitHub Pages | free (public repo) |
| Claude Haiku 4.5 (~150 items/day) | ≈ $0.10/day ≈ $3/month |

Future option: the Message Batches API halves LLM cost if latency stops mattering.
