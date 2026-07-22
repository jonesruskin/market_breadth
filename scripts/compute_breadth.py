"""
compute_breadth.py
-------------------
Run once per trading day (after NSE close). This is the script the
GitHub Action calls. It:

  1. Downloads today's full bhavcopy (all NSE mainboard equities).
  2. Appends it to the rolling price history (data/price_history.json).
  3. Computes Stockbee-style breadth indicators for today.
  4. Appends a summary row to data/breadth_timeseries.json (the time
     series the dashboard charts).
  5. Writes data/latest_snapshot.json (today's mover lists / new hi-lo
     lists / momentum-burst lists for the dashboard tables).

Usage:
    python scripts/compute_breadth.py               # today
    python scripts/compute_breadth.py 2026-07-22    # specific date (backfill/testing)
"""

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from nse_client import fetch_bhavcopy  # noqa: E402
import history_store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"  # lives under docs/ so GitHub Pages can serve it directly
HISTORY_PATH = DATA_DIR / "price_history.json"
TIMESERIES_PATH = DATA_DIR / "breadth_timeseries.json"
SNAPSHOT_PATH = DATA_DIR / "latest_snapshot.json"

MOVER_LIST_SIZE = 25
MOMENTUM_LIST_SIZE = 100  # cap so the JSON/table doesn't blow up on wide market moves


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def compute_for_date(target_date: dt.date):
    print(f"Fetching bhavcopy for {target_date}...")
    day_df = fetch_bhavcopy(target_date)
    if day_df.empty:
        print("No data returned (holiday or fetch issue) -- aborting.")
        return
    date_str = target_date.isoformat()
    print(f"Got {len(day_df)} symbols.")

    history = history_store.load(HISTORY_PATH)
    history = history_store.append_day(history, date_str, day_df)
    history_store.save(HISTORY_PATH, history)

    # Build a wide per-symbol frame from history for indicator math
    records = []
    for sym, rec in history.items():
        if rec["dates"][-1] != date_str:
            continue  # symbol didn't trade today, exclude from today's breadth
        closes = np.array(rec["close"], dtype=float)
        vols = np.array(rec["volume"], dtype=float)
        n = len(closes)
        today_close = closes[-1]
        prev_close = closes[-2] if n >= 2 else np.nan
        pct_chg = (today_close / prev_close - 1) * 100 if prev_close and prev_close > 0 else np.nan

        ma50 = closes[-50:].mean() if n >= 50 else np.nan
        ma150 = closes[-150:].mean() if n >= 150 else np.nan
        ma200 = closes[-200:].mean() if n >= 200 else np.nan

        lookback_year = closes[-252:] if n >= 2 else closes
        high_52w = lookback_year.max()
        low_52w = lookback_year.min()
        is_new_high = n >= 20 and today_close >= high_52w
        is_new_low = n >= 20 and today_close <= low_52w

        # 1-month (~21 trading day) move, for the 25%-in-a-month momentum club
        close_21_ago = closes[-22] if n >= 22 else np.nan
        pct_chg_1m = (
            (today_close / close_21_ago - 1) * 100
            if close_21_ago and close_21_ago > 0
            else np.nan
        )

        records.append(
            {
                "symbol": sym,
                "close": today_close,
                "pct_chg": pct_chg,
                "volume": vols[-1] if len(vols) else 0,
                "prev_volume": vols[-2] if len(vols) >= 2 else np.nan,
                "ma50": ma50,
                "ma150": ma150,
                "ma200": ma200,
                "above_50dma": (today_close > ma50) if not np.isnan(ma50) else None,
                "above_150dma": (today_close > ma150) if not np.isnan(ma150) else None,
                "above_200dma": (today_close > ma200) if not np.isnan(ma200) else None,
                "is_new_high": is_new_high,
                "is_new_low": is_new_low,
                "pct_chg_1m": pct_chg_1m,
                "days_tracked": n,
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        print("No usable records for today -- aborting.")
        return

    valid_chg = df["pct_chg"].dropna()
    advances = int((valid_chg > 0).sum())
    declines = int((valid_chg < 0).sum())
    unchanged = int((valid_chg == 0).sum())
    ad_ratio = round(advances / declines, 3) if declines else None

    def pct_true(col):
        s = df[col].dropna()
        return round(100 * s.sum() / len(s), 2) if len(s) else None

    pct_above_50 = pct_true("above_50dma")
    pct_above_150 = pct_true("above_150dma")
    pct_above_200 = pct_true("above_200dma")

    new_highs = df[df["is_new_high"]]
    new_lows = df[df["is_new_low"]]

    up4 = df[df["pct_chg"] >= 4]
    down4 = df[df["pct_chg"] <= -4]
    up25_month = df[df["pct_chg_1m"] >= 25]
    down25_month = df[df["pct_chg_1m"] <= -25]

    up_vol = df.loc[df["pct_chg"] > 0, "volume"].sum()
    down_vol = df.loc[df["pct_chg"] < 0, "volume"].sum()
    up_down_vol_ratio = round(up_vol / down_vol, 3) if down_vol else None

    summary = {
        "date": date_str,
        "total_symbols": int(len(df)),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "ad_ratio": ad_ratio,
        "pct_above_50dma": pct_above_50,
        "pct_above_150dma": pct_above_150,
        "pct_above_200dma": pct_above_200,
        "new_highs_count": int(len(new_highs)),
        "new_lows_count": int(len(new_lows)),
        "up_4pct_count": int(len(up4)),
        "down_4pct_count": int(len(down4)),
        "net_4pct": int(len(up4) - len(down4)),
        "up_25pct_month_count": int(len(up25_month)),
        "down_25pct_month_count": int(len(down25_month)),
        "up_down_volume_ratio": up_down_vol_ratio,
    }

    # ---- timeseries.json: append/replace today's row ----
    series = load_json_list(TIMESERIES_PATH)
    series = [r for r in series if r.get("date") != date_str]
    series.append(summary)
    series.sort(key=lambda r: r["date"])
    series = series[-750:]  # ~3 years of trading days
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TIMESERIES_PATH, "w") as f:
        json.dump(series, f, indent=2)

    # ---- latest_snapshot.json: today's tables for the dashboard ----
    def top_movers(frame, ascending, n):
        sub = frame.dropna(subset=["pct_chg"]).sort_values("pct_chg", ascending=ascending).head(n)
        return sub[["symbol", "close", "pct_chg"]].round(2).to_dict("records")

    snapshot = {
        "date": date_str,
        "summary": summary,
        "top_gainers": top_movers(df, False, MOVER_LIST_SIZE),
        "top_losers": top_movers(df, True, MOVER_LIST_SIZE),
        "new_highs": new_highs[["symbol", "close", "pct_chg"]]
        .round(2)
        .head(MOMENTUM_LIST_SIZE)
        .to_dict("records"),
        "new_lows": new_lows[["symbol", "close", "pct_chg"]]
        .round(2)
        .head(MOMENTUM_LIST_SIZE)
        .to_dict("records"),
        "up_4pct": up4[["symbol", "close", "pct_chg"]]
        .round(2)
        .sort_values("pct_chg", ascending=False)
        .head(MOMENTUM_LIST_SIZE)
        .to_dict("records"),
        "down_4pct": down4[["symbol", "close", "pct_chg"]]
        .round(2)
        .sort_values("pct_chg")
        .head(MOMENTUM_LIST_SIZE)
        .to_dict("records"),
    }
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    print("Done. Summary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = dt.date.fromisoformat(sys.argv[1])
    else:
        target = dt.date.today()
    compute_for_date(target)
