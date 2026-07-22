"""
backfill.py
-----------
Run this ONCE by hand (locally or via a manual GitHub Action run) before
turning on the daily schedule. It walks backwards from today and
downloads bhavcopy files for the last ~280 calendar days so that
50/150/200-day moving averages and 52-week highs/lows are meaningful
from the very first "real" daily run, instead of slowly filling in over
the next year.

This is the slowest and most fetch-heavy script here (up to ~280
requests, one per trading day, spaced out to be polite to NSE) -- expect
it to take a while. Weekends/holidays 404 and are skipped automatically.

Usage:
    python scripts/backfill.py             # last 280 calendar days
    python scripts/backfill.py 400         # custom lookback in days
"""

import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nse_client import fetch_bhavcopy, _session  # noqa: E402
import history_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "docs" / "data" / "price_history.json"


def backfill(lookback_days: int = 280):
    session = _session()
    history = history_store.load(HISTORY_PATH)

    today = dt.date.today()
    dates = [today - dt.timedelta(days=i) for i in range(lookback_days, -1, -1)]
    ok, skipped = 0, 0

    for d in dates:
        if d.weekday() >= 5:  # skip Sat/Sun, saves a request
            continue
        date_str = d.isoformat()
        try:
            df = fetch_bhavcopy(d, session=session)
            if df.empty:
                skipped += 1
                continue
            history = history_store.append_day(history, date_str, df)
            ok += 1
            print(f"{date_str}: {len(df)} symbols OK")
        except Exception as e:  # noqa: BLE001
            skipped += 1
            print(f"{date_str}: skipped ({e})")
        time.sleep(1.5)  # be polite -- avoid tripping rate limits

        # save progress periodically so a crash doesn't lose everything
        if ok % 20 == 0:
            history_store.save(HISTORY_PATH, history)

    history_store.save(HISTORY_PATH, history)
    print(f"\nBackfill complete. {ok} days loaded, {skipped} skipped (holidays/weekends/errors).")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 280
    backfill(days)
