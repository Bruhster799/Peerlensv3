"""Macro module: a simulated Indian macro environment, and the analysis that measures how sensitive
each company and industry is to it.

Why simulate macro data at all? On its own, invented GDP would say nothing about the real economy.
Here it plays a different role: the synthetic companies are *driven* by this macro path with a known,
built-in sensitivity per industry (the business rule "cyclical industries move more with GDP").
The analysis then has to recover those sensitivities from the statements alone. Because the true
values are known, we can prove the method works before trusting it on real data.

Macro rules (an India-like regime, not actual RBI or MoSPI figures):
  * Real GDP growth: trend 6.5% plus AR(1) noise; a pandemic shock in FY2021 and a rebound in FY2022.
  * CPI inflation: 5% plus a demand-pull link to the GDP gap, plus AR(1) noise, floor 2%.
  * Policy repo rate: a Taylor-style rule, responding to inflation and the output gap, kept in 3.5-8%.
  * INR per USD: drifts with the inflation gap versus the US (purchasing-power parity) plus noise.
"""
import numpy as np
import pandas as pd

TREND_GDP = 0.065
TARGET_CPI = 0.05
FIRST_YEAR, LAST_YEAR = 2006, 2025          # the full simulated span; datasets use a slice of it
SHOCKS = {"FY2021": -0.125, "FY2022": 0.045}  # pandemic contraction, then rebound (added to GDP growth)

MACRO_LABELS = {"gdp_growth": "Real GDP growth", "cpi_inflation": "CPI inflation",
                "repo_rate": "Policy repo rate", "inr_usd": "INR per USD"}


def generate_macro(seed=42):
    """One simulated macro path for FY2006-FY2025. Same seed, same path."""
    rng = np.random.default_rng([seed, 2025])
    rows, gdp_noise, cpi_noise, inr = [], 0.0, 0.0, 44.0
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        label = f"FY{year}"
        gdp_noise = 0.4 * gdp_noise + rng.normal(0, 0.012)
        gdp = TREND_GDP + gdp_noise + SHOCKS.get(label, 0.0)
        cpi_noise = 0.5 * cpi_noise + rng.normal(0, 0.008)
        cpi = max(TARGET_CPI + 0.25 * (gdp - TREND_GDP) + cpi_noise, 0.02)
        repo = float(np.clip(0.025 + 1.0 * cpi + 0.3 * (gdp - TREND_GDP), 0.035, 0.08))
        inr *= 1 + (cpi - 0.025) + 0.012 + rng.normal(0, 0.02)   # inflation gap plus a structural drift
        rows.append(dict(year=label, gdp_growth=gdp, cpi_inflation=cpi, repo_rate=repo, inr_usd=inr))
    return pd.DataFrame(rows)


def macro_for_years(years, seed=42):
    macro = generate_macro(seed).set_index("year")
    missing = [y for y in years if y not in macro.index]
    if missing:
        raise ValueError(f"Macro path covers FY{FIRST_YEAR}-FY{LAST_YEAR}; cannot supply {missing}")
    return macro.loc[list(years)].reset_index()


# --------------------------------------------------------------------------- analysis
MIN_YEARS = 6        # need at least 5 growth observations per company for a meaningful slope


def growth_panel(clean, macro):
    """One row per company-year: revenue growth and EBITDA margin next to the macro variables."""
    data = clean.sort_values(["company", "year"]).copy()
    data["revenue_growth"] = data.groupby("company")["revenue"].pct_change()
    data["ebitda_margin"] = data["ebitda"] / data["revenue"]
    data["margin_change"] = data.groupby("company")["ebitda_margin"].diff()
    panel = data.merge(macro, on="year", how="inner")
    return panel.dropna(subset=["revenue_growth"])


def _ols(x, y):
    """Slope, standard error, p-value and R² from statsmodels OLS; NaN when there is too little data."""
    import statsmodels.api as sm
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x)[mask], np.asarray(y)[mask]
    if len(x) < 4 or np.std(x) == 0:
        return dict(alpha=np.nan, beta=np.nan, se=np.nan, p_value=np.nan, r2=np.nan, n=len(x))
    model = sm.OLS(y, sm.add_constant(x)).fit()
    return dict(alpha=model.params[0], beta=model.params[1], se=model.bse[1], p_value=model.pvalues[1],
                r2=model.rsquared, n=len(x))


def classify(beta):
    if pd.isna(beta):
        return "n/a"
    if beta >= 1.3:
        return "Highly cyclical"
    if beta >= 0.7:
        return "Cyclical"
    if beta >= 0.3:
        return "Moderately defensive"
    return "Defensive"


def gdp_sensitivity(panel):
    """Per-company GDP beta: extra revenue growth (pp) for each extra 1pp of real GDP growth."""
    records = []
    for company, group in panel.groupby("company"):
        fit = _ols(group["gdp_growth"].values, group["revenue_growth"].values)
        records.append(dict(company=company, **fit, profile=classify(fit["beta"])))
    return pd.DataFrame(records)


def pooled_sensitivity(panel):
    """Industry-level betas from all peers pooled together (more observations, tighter estimate)."""
    gdp = _ols(panel["gdp_growth"].values, panel["revenue_growth"].values)
    margin = _ols(panel["cpi_inflation"].values, panel["margin_change"].values)
    return dict(gdp_beta=gdp["beta"], gdp_se=gdp["se"], gdp_p=gdp["p_value"], gdp_r2=gdp["r2"], n=gdp["n"],
                inflation_margin_beta=margin["beta"], inflation_p=margin["p_value"],
                profile=classify(gdp["beta"]))


def change_correlations(macro, panel):
    """Correlations of year-on-year CHANGES, not levels. Trending levels correlate spuriously; growth
    rates and differences do not share a trend, so their correlations mean something."""
    industry = panel.groupby("year").agg(revenue_growth=("revenue_growth", "median"),
                                         margin_change=("margin_change", "median"))
    changes = macro.set_index("year")[["gdp_growth", "cpi_inflation"]].copy()
    changes["repo_rate_change"] = macro.set_index("year")["repo_rate"].diff()
    changes["inr_depreciation"] = macro.set_index("year")["inr_usd"].pct_change()
    table = changes.join(industry, how="inner").dropna()
    names = {"gdp_growth": "GDP growth", "cpi_inflation": "CPI inflation", "repo_rate_change": "Repo rate change",
             "inr_depreciation": "INR depreciation", "revenue_growth": "Industry revenue growth",
             "margin_change": "Industry margin change"}
    return table.rename(columns=names).corr()


def moving_averages(macro, panel, window=3):
    industry = panel.groupby("year")["revenue_growth"].median().rename("industry_growth")
    table = macro.set_index("year")[["gdp_growth"]].join(industry, how="inner")
    table[f"gdp_{window}y_ma"] = table["gdp_growth"].rolling(window).mean()
    table[f"industry_{window}y_ma"] = table["industry_growth"].rolling(window).mean()
    return table.reset_index()


def scenario(sensitivity, gdp_next):
    """Projected revenue growth for each company if next year's real GDP growth is `gdp_next`:
    the company's own baseline (regression intercept) plus its GDP beta times the scenario."""
    table = sensitivity[["company", "alpha", "beta", "profile"]].copy()
    table["projected_growth"] = table["alpha"] + table["beta"] * gdp_next
    return table.sort_values("projected_growth", ascending=False)


def headline(industry, pooled):
    """One plain-language sentence a manager can act on."""
    if pd.isna(pooled["gdp_beta"]):
        return "Not enough years of data to estimate sensitivity to the economy."
    significant = pooled["gdp_p"] < 0.05
    direction = "amplifies" if pooled["gdp_beta"] > 1 else "dampens"
    text = (f"{industry} is {pooled['profile'].lower()}: each extra 1 percentage point of GDP growth moves "
            f"revenue growth by about {pooled['gdp_beta']:.1f} pp, so the industry {direction} the economic "
            f"cycle")
    text += (f" (statistically significant, p = {pooled['gdp_p']:.3f})." if significant
             else f" (not statistically significant, p = {pooled['gdp_p']:.2f}; treat with caution).")
    return text
