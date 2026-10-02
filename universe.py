"""Loads the Nifty 500 constituent list (company, industry, NSE symbol)."""
import io
from pathlib import Path

import pandas as pd
import requests

NSE_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
MIRROR_URL = ("https://raw.githubusercontent.com/pkjmesra/PKScreener/"
              "actions-data-download/results/Indices/ind_nifty500list.csv")
BUNDLED_FILE = Path(__file__).resolve().parent.parent / "data" / "nifty500.csv"
REQUIRED_COLUMNS = ["Company Name", "Industry", "Symbol"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _clean(raw):
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Constituent file is missing columns: {missing}")
    data = raw[REQUIRED_COLUMNS].rename(columns={"Company Name": "company", "Industry": "industry",
                                                 "Symbol": "symbol"})
    data = data.dropna().drop_duplicates("symbol")
    data["company"] = data["company"].str.replace(r"\s*Ltd\.?$", "", regex=True).str.strip()
    data["yahoo_symbol"] = data["symbol"] + ".NS"
    return data.sort_values(["industry", "company"]).reset_index(drop=True)


def load_nifty500(allow_network=True, timeout=8):
    """Try NSE first, then a GitHub mirror, then the snapshot bundled with the app.

    Returns (DataFrame, source_label)."""
    if allow_network:
        for label, url in (("NSE India (live)", NSE_URL), ("GitHub mirror of the NSE file", MIRROR_URL)):
            try:
                response = requests.get(url, headers=HEADERS, timeout=timeout)
                response.raise_for_status()
                data = _clean(pd.read_csv(io.StringIO(response.text)))
                if len(data) >= 450:          # sanity check: a real Nifty 500 list
                    return data, label
            except Exception:
                continue
    return _clean(pd.read_csv(BUNDLED_FILE)), "Bundled snapshot"
