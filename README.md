# NSE Market Breadth Dashboard

A Stockbee-style market breadth dashboard for all NSE mainboard equities
(EQ/BE series) that updates itself automatically every trading day —
no manual data entry.

**How it works**
- A Python script downloads NSE's daily "bhavcopy" (the official EOD
  price/volume file covering every listed stock) and computes breadth
  indicators.
- A GitHub Action runs that script on a schedule every weekday evening
  and commits the results back to this repo — this is the automation,
  it runs on GitHub's servers, not your computer.
- A static dashboard (`docs/index.html`), hosted for free on GitHub
  Pages, reads those results and renders the charts/tables. Just
  bookmark the Pages URL and check it after market close.

**What it shows** (see `docs/index.html`):
- Advances / Declines / A-D ratio
- % of stocks above 50 / 150 / 200-day moving average
- New 52-week highs vs lows
- Up/down volume ratio
- "Momentum burst" — stocks up/down ≥4% in a day, and ≥25% in a month
  (Stockbee's signature breadth indicators)
- Top gainers/losers, new-high/new-low lists, 4%-club lists

---

## Setup (one-time, ~15 minutes)

### 1. Create the repo
Create a **new GitHub repository** (public is fine and free; private
also works but Pages requires a paid plan for private repos). Upload
everything in this project folder to it, preserving the folder
structure (`.github/workflows/`, `scripts/`, `docs/`).

If you're comfortable with git:
```bash
cd nse-market-breadth
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```
Otherwise: on github.com, create the repo, then use "Add file → Upload
files" and drag the whole folder in (make sure hidden folders like
`.github` come along — the web uploader sometimes hides dotfiles, so
git is more reliable for that folder specifically).

### 2. Enable GitHub Pages
Repo → **Settings → Pages** → under "Build and deployment", set
**Source: Deploy from a branch**, **Branch: main**, **Folder: /docs**
→ Save. GitHub will give you a URL like
`https://<your-username>.github.io/<your-repo>/` — that's your
dashboard link. Bookmark it.

### 3. Allow the Action to push commits
Repo → **Settings → Actions → General** → scroll to "Workflow
permissions" → select **"Read and write permissions"** → Save. (The
daily workflow needs this to commit each day's data back to the repo.)

### 4. Backfill history (important — do this before relying on it)
Moving averages and 52-week highs/lows need past data. Run the
backfill once, either:

**Locally** (recommended — easier to watch for errors):
```bash
pip install -r scripts/requirements.txt
python scripts/backfill.py        # takes several minutes, ~280 requests
git add docs/data && git commit -m "Backfill history" && git push
```

**Or via GitHub Actions**: temporarily add `workflow_dispatch` steps
that call `backfill.py` instead of `compute_breadth.py`, run it once
from the Actions tab, then revert. Doing it locally is simpler.

### 5. Test the daily script once
```bash
python scripts/compute_breadth.py
```
This fetches *today's* bhavcopy and writes `docs/data/*.json`. Open
`docs/index.html` locally (or push and visit your Pages URL) to check
it renders.

### 6. Let it run
The workflow in `.github/workflows/daily-breadth.yml` is scheduled for
11:15 UTC (4:45 PM IST) on weekdays. It will silently do nothing on
exchange holidays (the bhavcopy file won't exist, and the script exits
cleanly). You can also trigger it manually any time from the repo's
**Actions** tab → "Daily NSE Market Breadth" → "Run workflow".

---

## If the automated fetch stops working

This is the one real risk with any NSE automation: **NSE's website
actively blocks traffic that doesn't look like a real browser**, and
its anti-bot measures change over time. `scripts/nse_client.py` uses
the same session/cookie approach as well-known open source NSE tools,
but if GitHub Action runs start failing:

1. Check the failed run's logs (Actions tab) for the actual error.
2. Try running `python scripts/compute_breadth.py` from your own
   machine/network — if it works locally but not from GitHub Actions,
   NSE is likely blocking GitHub's IP ranges specifically. In that
   case, switch the schedule to run on a machine you control (e.g. a
   Raspberry Pi, a home server, or your laptop via cron/Task Scheduler
   at market close) instead of GitHub Actions — the dashboard and data
   format stay identical either way.
3. As a fallback data source, `yfinance` (Yahoo Finance, tickers like
   `RELIANCE.NS`) is generally more tolerant of automated access than
   NSE directly, but requires one request per stock rather than one
   file for the whole exchange, so it's slower for "all NSE stocks."

## Customizing

- **Smaller universe**: to track only Nifty 500 / Nifty 200 instead of
  all stocks, filter `day_df` in `compute_breadth.py` against a symbol
  list before computing indicators — faster runs, smaller repo.
- **Different momentum thresholds**: the ≥4%/day and ≥25%/month
  cutoffs are set as literals in `compute_breadth.py` (search for
  `>= 4` and `>= 25`) — change them there.
- **Schedule time**: edit the cron line in
  `.github/workflows/daily-breadth.yml` (cron is in UTC).

## Notes

- This is for personal research, not investment advice.
- Series filter keeps `EQ` and `BE` (mainboard equity series) and
  excludes bonds, ETFs, SME-listed stocks, etc. Adjust in
  `nse_client.py` if you want a different scope.
