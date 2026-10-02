"""Synthetic financial statements for any set of Nifty 500 companies, driven by a simulated macro path.

Used for Demo mode (works offline, never rate-limited) and for the course's data-generator
requirement. Every company gets randomised parameters drawn around its industry's archetype.

Business rules built in:
  * revenue growth = company trend + industry GDP beta x (GDP growth - trend GDP) + noise,
    so cyclical industries (metals, cement, realty) swing with the economy and defensive ones do not
  * EBITDA margin falls when CPI inflation runs above target, for industries with input-cost exposure,
    and takes an industry-specific cost shock in FY2023
  * fixed assets = revenue / fixed-asset turnover; depreciation = 5% of fixed assets
  * interest = (policy repo rate + credit spread) x opening debt, so rate hikes raise interest costs
  * tax = 25% of profit before tax (only when profitable)
  * equity grows by retained profit; cash is the balancing figure, so
    Total assets = Equity + Debt + Current liabilities always holds
  * solvency: if equity falls below 15% of assets (8% for lenders), the company raises fresh equity
"""
import zlib

import numpy as np
import pandas as pd

from .macro import TARGET_CPI, TREND_GDP, macro_for_years
from .schema import ALL_COLUMNS

YEARS = [f"FY{y}" for y in range(2016, 2026)]        # ten financial years, FY2016 to FY2025
DEPRECIATION_RATE = 0.05
CREDIT_SPREAD = 0.03                                   # corporate borrowing rate = repo + 3%
TAX_RATE = 0.25
MIN_CASH_SHARE = 0.03
COST_SHOCK_YEAR = "FY2023"

# margin = EBITDA / revenue, fa_turnover = revenue / fixed assets, leverage = debt / fixed assets,
# days = inventory, receivable and payable days, growth = average revenue growth, pe = typical P/E,
# gdp_beta = revenue sensitivity to the GDP cycle, inflation_sensitivity = margin squeeze from CPI
DEFAULT_ARCHETYPE = dict(margin=0.16, fa_turnover=1.6, leverage=0.35, inventory_days=45,
                         receivable_days=40, payable_days=55, growth=0.11, pe=32, shock=-0.08,
                         depreciation_rate=DEPRECIATION_RATE, credit_spread=CREDIT_SPREAD,
                         gdp_beta=1.0, inflation_sensitivity=0.6)
ARCHETYPES = {
    "Information Technology": dict(margin=0.24, fa_turnover=6.0, leverage=0.05, inventory_days=0,
                                   receivable_days=70, payable_days=30, growth=0.12, pe=30, shock=-0.03,
                                   gdp_beta=0.4, inflation_sensitivity=0.2),
    "Construction Materials": dict(margin=0.18, fa_turnover=0.9, leverage=0.30, inventory_days=35,
                                   receivable_days=12, payable_days=60, growth=0.10, pe=40, shock=-0.22,
                                   gdp_beta=1.6, inflation_sensitivity=1.0),
    "Fast Moving Consumer Goods": dict(margin=0.21, fa_turnover=3.5, leverage=0.10, inventory_days=40,
                                       receivable_days=15, payable_days=65, growth=0.09, pe=55, shock=-0.10,
                                       gdp_beta=0.35, inflation_sensitivity=1.5),
    "Metals & Mining": dict(margin=0.17, fa_turnover=1.0, leverage=0.55, inventory_days=70,
                            receivable_days=25, payable_days=60, growth=0.08, pe=14, shock=-0.25,
                            gdp_beta=2.0, inflation_sensitivity=0.4),
    "Healthcare": dict(margin=0.22, fa_turnover=2.2, leverage=0.15, inventory_days=90,
                       receivable_days=75, payable_days=60, growth=0.11, pe=38, shock=-0.05,
                       gdp_beta=0.3, inflation_sensitivity=0.5),
    "Automobile and Auto Components": dict(margin=0.13, fa_turnover=2.0, leverage=0.25, inventory_days=35,
                                           receivable_days=30, payable_days=70, growth=0.12, pe=28, shock=-0.12,
                                           gdp_beta=1.8, inflation_sensitivity=1.0),
    "Power": dict(margin=0.30, fa_turnover=0.4, leverage=0.60, inventory_days=20,
                  receivable_days=60, payable_days=45, growth=0.09, pe=20, shock=-0.05,
                  gdp_beta=0.8, inflation_sensitivity=0.3),
    "Realty": dict(gdp_beta=2.2, inflation_sensitivity=0.8, leverage=0.40, fa_turnover=0.6, inventory_days=250,
                   margin=0.24),
    "Capital Goods": dict(gdp_beta=1.5, inflation_sensitivity=0.9),
    "Construction": dict(gdp_beta=1.6, inflation_sensitivity=1.0, leverage=0.45),
    "Consumer Durables": dict(gdp_beta=1.3, inflation_sensitivity=1.2),
    "Chemicals": dict(gdp_beta=1.1, inflation_sensitivity=1.1),
    "Telecommunication": dict(gdp_beta=0.5, inflation_sensitivity=0.3, leverage=0.65, fa_turnover=0.6),
    # For lenders the "fixed assets" stand in for the loan book: revenue is interest income, interest
    # expense is the cost of deposits and borrowings (repo + 0.5%), and there is little depreciation.
    "Financial Services": dict(margin=0.80, fa_turnover=0.11, leverage=0.80, inventory_days=0,
                               receivable_days=5, payable_days=20, growth=0.15, pe=22, shock=-0.04,
                               depreciation_rate=0.004, credit_spread=0.005, gdp_beta=1.2,
                               inflation_sensitivity=0.0),
}


def archetype_for(industry):
    return {**DEFAULT_ARCHETYPE, **ARCHETYPES.get(industry, {})}


def _company_rows(company, symbol, archetype, macro, rng):
    # --- company-level draws: each company is a noisy version of its industry archetype ---
    size_revenue = float(rng.lognormal(mean=8.9, sigma=0.6))       # ≈ ₹7,300 crore median in FY2016
    margin = max(archetype["margin"] * rng.normal(1, 0.18), 0.03)
    fa_turnover = archetype["fa_turnover"] * rng.normal(1, 0.15)
    if archetype["leverage"] >= 0.8:                               # lenders: leverage is structural
        leverage = min(archetype["leverage"] * rng.normal(1, 0.04), 0.88)
    else:
        leverage = min(max(archetype["leverage"] * rng.normal(1, 0.45), 0.0), 0.75)
        if rng.random() < 0.2:
            leverage = 0.0                                         # some companies are debt-free
    growth = archetype["growth"] * rng.normal(1, 0.35)
    gdp_beta = archetype["gdp_beta"] * rng.normal(1, 0.15)         # the company's own cyclicality
    days = {k: archetype[k] * max(rng.normal(1, 0.2), 0.3)
            for k in ("inventory_days", "receivable_days", "payable_days")}

    rows, equity, opening_debt, revenue = [], None, None, size_revenue
    for index, m in enumerate(macro.itertuples(index=False)):
        # --- revenue follows the economy, scaled by the company's GDP beta ---
        if index > 0:
            year_growth = growth + gdp_beta * (m.gdp_growth - TREND_GDP) + rng.normal(0, 0.03)
            revenue *= max(1 + year_growth, 0.3)
        # --- margin: noise, inflation squeeze, and the industry cost shock ---
        inflation_squeeze = 1 - archetype["inflation_sensitivity"] * (m.cpi_inflation - TARGET_CPI) * 5
        year_margin = (margin * rng.normal(1, 0.07) * max(inflation_squeeze, 0.5)
                       * (1 + (archetype["shock"] if m.year == COST_SHOCK_YEAR else 0)))
        ebitda = revenue * year_margin
        fixed_assets = revenue / fa_turnover
        depreciation = fixed_assets * archetype["depreciation_rate"]
        debt = fixed_assets * leverage * rng.normal(1, 0.05)
        borrowing_rate = m.repo_rate + archetype["credit_spread"]
        interest = (opening_debt if opening_debt is not None else debt) * borrowing_rate
        ebit = ebitda - depreciation
        pretax = ebit - interest
        tax = TAX_RATE * max(pretax, 0)
        net_income = pretax - tax

        inventory = revenue * days["inventory_days"] / 365
        receivables = revenue * days["receivable_days"] / 365
        current_liabilities = revenue * days["payable_days"] / 365

        if equity is None:
            opening_cash = revenue * rng.uniform(0.05, 0.20)
            equity = fixed_assets + inventory + receivables + opening_cash - debt - current_liabilities
        else:
            equity += net_income * (1 - rng.uniform(0.1, 0.4))     # retain 60-90% of profit

        cash = equity + debt + current_liabilities - fixed_assets - inventory - receivables
        if cash < MIN_CASH_SHARE * revenue:                          # borrow any shortfall
            debt += MIN_CASH_SHARE * revenue - cash
            cash = MIN_CASH_SHARE * revenue

        # --- solvency rule: below 15% equity, the company recapitalises (rights issue) back to 20% ---
        total_assets = fixed_assets + inventory + receivables + cash
        floor = 0.08 if archetype["leverage"] >= 0.8 else 0.15            # lenders run thinner equity
        if equity < floor * total_assets:
            injection = (floor + 0.05) * total_assets - equity
            equity += injection
            cash += injection

        current_assets = inventory + receivables + cash
        rows.append(dict(company=company, symbol=symbol, year=m.year, revenue=revenue, ebitda=ebitda,
                         ebit=ebit, depreciation=depreciation, interest=interest, pretax_income=pretax,
                         tax=tax, net_income=net_income, total_assets=fixed_assets + current_assets,
                         current_assets=current_assets, current_liabilities=current_liabilities,
                         inventory=inventory, receivables=receivables, cash=cash, total_debt=debt,
                         equity=equity))
        opening_debt = debt
    return rows


def generate_financials(companies, industry, seed=42, inject_errors=False, years=None):
    """companies: DataFrame with 'company' and 'symbol'. Returns a table in the standard schema."""
    years = list(years or YEARS)
    macro = macro_for_years(years, seed)
    archetype = archetype_for(industry)
    rows = []
    for record in companies.itertuples(index=False):
        # a per-company generator keeps each company's numbers stable whichever peers are chosen
        company_rng = np.random.default_rng([seed, zlib.crc32(record.symbol.encode())])
        rows.extend(_company_rows(record.company, record.symbol, archetype, macro, company_rng))
    data = pd.DataFrame(rows, columns=ALL_COLUMNS)
    numeric = data.columns[3:]
    data[numeric] = data[numeric].round(1)
    data["current_assets"] = data[["inventory", "receivables", "cash"]].sum(axis=1).round(1)
    fixed = (data["total_assets"] - data["current_assets"]).round(1)
    data["total_assets"] = (fixed + data["current_assets"]).round(1)
    data["equity"] = (data["total_assets"] - data["total_debt"] - data["current_liabilities"]).round(1)

    if inject_errors and len(data) >= 3 * len(years) and len(years) >= 3:
        symbols = data["symbol"].unique()
        # 1) missing value   2) sign error   3) duplicated row
        data.loc[(data.symbol == symbols[1]) & (data.year == years[-3]), "receivables"] = np.nan
        mask = (data.symbol == symbols[2]) & (data.year == years[0])
        # flip the sign of inventory, or receivables when the company carries no inventory (IT, lenders)
        field = "inventory" if (data.loc[mask, "inventory"] > 0).all() else "receivables"
        data.loc[mask, field] = -data.loc[mask, field]
        data = pd.concat([data, data[(data.symbol == symbols[0]) & (data.year == years[-2])]],
                         ignore_index=True)
    return data


def true_gdp_beta(industry):
    """The sensitivity built into the generator, used to check the analysis recovers it."""
    return archetype_for(industry)["gdp_beta"]


def generate_market_snapshot(companies, industry, seed=42):
    """Market cap (₹ crore), P/E and P/B for demo mode, consistent with the generated financials."""
    financials = generate_financials(companies, industry, seed)
    latest = financials[financials.year == YEARS[-1]].set_index("symbol")
    rng = np.random.default_rng(seed + 1)
    pe_base = archetype_for(industry)["pe"]
    records = []
    for symbol, row in latest.iterrows():
        pe = max(pe_base * rng.normal(1, 0.3), 6)
        market_cap = max(row.net_income, row.revenue * 0.01) * pe
        records.append(dict(symbol=symbol, market_cap=market_cap, pe=pe,
                            pb=market_cap / row.equity if row.equity > 0 else np.nan))
    return pd.DataFrame(records)


def generate_prices(symbols, seed=42, days=250):
    """Simulated one-year daily price paths (geometric Brownian motion), rebased to 100."""
    rng = np.random.default_rng(seed + 7)
    dates = pd.bdate_range(end=pd.Timestamp("2026-09-25"), periods=days)
    prices = {}
    for symbol in symbols:
        drift, vol = rng.normal(0.12, 0.12) / days, rng.uniform(0.18, 0.40) / np.sqrt(days)
        prices[symbol] = 100 * np.exp(np.cumsum(rng.normal(drift, vol, days)))
    return pd.DataFrame(prices, index=dates)
