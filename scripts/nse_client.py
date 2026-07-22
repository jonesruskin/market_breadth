"""
nse_client.py
--------------
Small helper for pulling the full daily "bhavcopy" (EOD price/volume file
covering every stock traded on NSE that day) from NSE's public archives.

NSE does not have an official developer API, and its website actively
blocks requests that don't look like a real browser (missing cookies,
missing Referer, generic User-Agent, etc). The pattern below -- visit the
homepage first to pick up session cookies, then request the CSV with
browser-like headers -- is the same approach used by well known open
source NSE tools (jugaad-data, nsepython). It is NOT guaranteed to keep
working forever: if NSE changes its anti-bot measures this will need
updating. See README.md "If the automated fetch stops working" section.
"""

import datetime as dt
import io
import time

import pandas as pd
import requests

BASE_HOST = "https://www.nseindia.com"
ARCHIVE_URL = (
    "https://nsearchives.nseindia.com/products/content/"
    "sec_bhavdata_full_{date_str}.csv"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _session() -> requests.Session:
    """Create a session with cookies picked up from the NSE homepage.

    NSE rejects the bhavcopy request outright if it doesn't carry cookies
    set by an earlier visit to nseindia.com, so we always hit the homepage
    (and the equities landing page, which sets a couple more cookies)
    before asking for the CSV.
    """
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(BASE_HOST, timeout=15)
    time.sleep(1)
    s.get(f"{BASE_HOST}/market-data/securities-available-for-trading", timeout=15)
    time.sleep(1)
    return s


def fetch_bhavcopy(date: dt.date, session: requests.Session | None = None) -> pd.DataFrame:
    """Download and parse the full bhavcopy CSV for a single trading date.

    Returns a DataFrame with (at least) columns:
        SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE,
        LOW_PRICE, CLOSE_PRICE, TTL_TRD_QNTY (volume)
    Raises requests.HTTPError if the file for that date doesn't exist
    (e.g. weekend / exchange holiday) or requests.RequestException on
    network problems.
    """
    date_str = date.strftime("%d%m%Y")
    url = ARCHIVE_URL.format(date_str=date_str)
    sess = session or _session()
    resp = sess.get(url, timeout=20)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]

    # Keep only the equity series (EQ, BE) -- excludes bonds/ETFs/SME etc.
    # so breadth reflects mainboard equities.
    if "SERIES" in df.columns:
        df = df[df["SERIES"].str.strip().isin(["EQ", "BE"])].copy()

    rename_map = {
        "SYMBOL": "symbol",
        "CLOSE_PRICE": "close",
        "PREV_CLOSE": "prev_close",
        "OPEN_PRICE": "open",
        "HIGH_PRICE": "high",
        "LOW_PRICE": "low",
        "TTL_TRD_QNTY": "volume",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    keep = ["symbol", "open", "high", "low", "close", "prev_close", "volume"]
    df = df[[c for c in keep if c in df.columns]]
    for col in ["open", "high", "low", "close", "prev_close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["symbol", "close"])
    df["symbol"] = df["symbol"].str.strip()
    df = df.drop_duplicates(subset="symbol", keep="last").reset_index(drop=True)
    return df
