"""
history_store.py
-----------------
Keeps a compact rolling per-symbol price/volume history on disk
(data/price_history.json) so we can compute 50/150/200-day moving
averages and 52-week highs/lows without re-downloading the past.

Format:
{
  "SYMBOL": {
    "dates":  ["2025-07-21", "2025-07-22", ...],
    "close":  [101.2, 102.4, ...],
    "volume": [123456, 98765, ...]
  },
  ...
}

We only keep the most recent MAX_DAYS trading days per symbol (a little
more than one year, enough for 200dma + 52-week high/low) to keep the
file small enough to live comfortably in a git repo.
"""

import json
from pathlib import Path

MAX_DAYS = 280  # ~13 months of trading days -- covers 200dma + 52w hi/lo


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def save(path: Path, history: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(history, f, separators=(",", ":"))


def append_day(history: dict, date_str: str, day_df) -> dict:
    """Append one day's bhavcopy DataFrame (symbol, close, volume) to history.

    Skips symbols already recorded for this date (idempotent re-runs).
    """
    for row in day_df.itertuples(index=False):
        sym = row.symbol
        rec = history.setdefault(sym, {"dates": [], "close": [], "volume": []})
        if rec["dates"] and rec["dates"][-1] == date_str:
            # already recorded today for this symbol -- overwrite (re-run)
            rec["close"][-1] = float(row.close)
            rec["volume"][-1] = float(getattr(row, "volume", 0) or 0)
        else:
            rec["dates"].append(date_str)
            rec["close"].append(float(row.close))
            rec["volume"].append(float(getattr(row, "volume", 0) or 0))
        # trim
        if len(rec["dates"]) > MAX_DAYS:
            rec["dates"] = rec["dates"][-MAX_DAYS:]
            rec["close"] = rec["close"][-MAX_DAYS:]
            rec["volume"] = rec["volume"][-MAX_DAYS:]
    return history
