"""Live data from Yahoo Finance (via yfinance), converted to the standard schema in ₹ crore."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .schema import ALL_COLUMNS, fiscal_year_label

CRORE = 1e7

# Yahoo's line-item names differ between companies, so each field lists fallbacks in priority order
INCOME_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT", "Operating Income"],
    "depreciation": ["Reconciled Depreciation", "Depreciation And Amortization In Income Statement",
                     "Depreciation And Amortization"],
    "interest": ["Interest Expense", "Interest Expense Non Operating"],
    "pretax_income": ["Pretax Income"],
    "tax": ["Tax Provision"],
    "net_income": ["Net Income", "Net Income Common Stockholders",
                   "Net Income From Continuing Operation Net Minority Interest"],
}
BALANCE_MAP = {
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "inventory": ["Inventory"],
    "receivables": ["Accounts Receivable", "Receivables"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "total_debt": ["Total Debt"],
    "equity": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
}


class LiveDataError(Exception):
    """Raised when Yahoo Finance returns nothing usable (often rate limiting)."""


def _pick(statement, candidates):
    """Return the first matching row of a yfinance statement, or an all-NaN row."""
    for name in candidates:
        if name in statement.index:
            return statement.loc[name]
    return pd.Series(np.nan, index=statement.columns)


def standardise_statements(income, balance, company, symbol):
    """Turn yfinance's wide statements (rows = items, columns = dates) into schema rows."""
    if income is None or balance is None or income.empty or balance.empty:
        return pd.DataFrame(columns=ALL_COLUMNS)
    items = {field: _pick(income, names) for field, names in INCOME_MAP.items()}
    items.update({field: _pick(balance, names) for field, names in BALANCE_MAP.items()})
    frame = pd.DataFrame(items)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.apply(pd.to_numeric, errors="coerce") / CRORE
    if "ebit" in frame and frame["ebitda"].isna().all():
        frame["ebitda"] = frame["ebit"] + frame["depreciation"]
    frame["interest"] = frame["interest"].abs()
    frame["year"] = [fiscal_year_label(ts) for ts in frame.index]
    frame["company"], frame["symbol"] = company, symbol
    frame = frame.dropna(subset=["revenue", "total_assets"], how="all")
    return frame.sort_values("year")[ALL_COLUMNS].reset_index(drop=True)


def fetch_financials(company, yahoo_symbol):
    import yfinance as yf
    ticker = yf.Ticker(yahoo_symbol)
    return standardise_statements(ticker.income_stmt, ticker.balance_sheet, company,
                                  yahoo_symbol.replace(".NS", ""))


def fetch_many_financials(companies, max_workers=6):
    """companies: DataFrame with company, yahoo_symbol. Returns (data, list_of_failed_companies)."""
    frames, failed = [], []

    def task(record):
        try:
            return record.company, fetch_financials(record.company, record.yahoo_symbol)
        except Exception:
            return record.company, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for company, frame in pool.map(task, companies.itertuples(index=False)):
            if frame is None or frame.empty:
                failed.append(company)
            else:
                frames.append(frame)
    if not frames:
        raise LiveDataError("Yahoo Finance returned no statements for any selected company.")
    return pd.concat(frames, ignore_index=True), failed


def fetch_market_snapshot(companies, max_workers=8):
    """Market cap (₹ crore), trailing P/E and P/B for each company; NaN where unavailable."""
    import yfinance as yf

    def task(record):
        result = dict(symbol=record.symbol, market_cap=np.nan, pe=np.nan, pb=np.nan)
        try:
            fast = yf.Ticker(record.yahoo_symbol).fast_info
            result["market_cap"] = float(fast["marketCap"]) / CRORE
        except Exception:
            pass
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        snapshot = pd.DataFrame(pool.map(task, companies.itertuples(index=False)))
    if snapshot["market_cap"].isna().all():
        raise LiveDataError("Yahoo Finance returned no market caps (the server may be rate-limited).")
    return snapshot


def fetch_valuation(yahoo_symbols):
    """Trailing P/E and price-to-book for the chosen peers (one request each)."""
    import yfinance as yf
    records = []
    for symbol in yahoo_symbols:
        try:
            info = yf.Ticker(symbol).info
            records.append(dict(symbol=symbol.replace(".NS", ""), pe=info.get("trailingPE", np.nan),
                                pb=info.get("priceToBook", np.nan)))
        except Exception:
            records.append(dict(symbol=symbol.replace(".NS", ""), pe=np.nan, pb=np.nan))
    return pd.DataFrame(records)


def fetch_prices(yahoo_symbols, period="1y"):
    """Daily closing prices rebased to 100 at the start of the period."""
    import yfinance as yf
    prices = yf.download(list(yahoo_symbols), period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(prices, pd.Series):
        prices = prices.to_frame(yahoo_symbols[0])
    prices = prices.dropna(how="all").ffill()
    if prices.empty:
        raise LiveDataError("No price history returned.")
    prices.columns = [c.replace(".NS", "") for c in prices.columns]
    return prices / prices.bfill().iloc[0] * 100
