"""Ratio definitions, rating, peer scoring and plain-language recommendations.

Each Ratio is defined once as signed numerator / denominator terms. That single definition drives
the pandas calculation, the Green/Amber/Red rating and the live Excel formula, so the app and the
exported workbook can never disagree.
"""
import numpy as np
import pandas as pd


def safe_divide(numerator, denominator):
    """Element-wise division; zero or missing denominators give NaN instead of an error or infinity."""
    numerator = pd.Series(numerator, dtype="float64")
    denominator = pd.Series(denominator, dtype="float64").replace(0, np.nan)
    return (numerator / denominator).replace([np.inf, -np.inf], np.nan)


class Ratio:
    def __init__(self, key, name, short, category, numerator, denominator, higher_is_better,
                 green, amber, unit, multiplier=1.0, action=""):
        self.key, self.name, self.short, self.category = key, name, short, category
        self.numerator, self.denominator = numerator, denominator     # lists of (column, +1/-1)
        self.higher_is_better = higher_is_better
        self.green, self.amber = green, amber
        self.unit, self.multiplier, self.action = unit, multiplier, action

    @staticmethod
    def _combine(data, terms):
        # min_count=len(terms): if any term is missing the whole expression is missing
        parts = pd.concat([sign * data[col].astype("float64") for col, sign in terms], axis=1)
        return parts.sum(axis=1, min_count=len(terms))

    def compute(self, data):
        values = safe_divide(self._combine(data, self.numerator).values,
                             self._combine(data, self.denominator).values)
        return (values * self.multiplier).values

    def rate(self, value):
        if value is None or pd.isna(value):
            return "n/a"
        if self.higher_is_better:
            return "Green" if value >= self.green else "Amber" if value >= self.amber else "Red"
        return "Green" if value <= self.green else "Amber" if value <= self.amber else "Red"

    def format(self, value):
        if value is None or pd.isna(value):
            return "n/a"
        if self.unit == "%":
            return f"{value:.1%}"
        if self.unit == "days":
            return f"{value:.0f} days"
        return f"{value:.2f}x"

    def excel_formula(self, column_letters, row, sheet="Data"):
        def expression(terms):
            text = "".join(("+" if sign > 0 else "-") + f"{sheet}!{column_letters[col]}{row}"
                           for col, sign in terms)
            return "(" + text.lstrip("+") + ")"
        num, den = expression(self.numerator), expression(self.denominator)
        return f'=IFERROR(IF({den}=0,"",{num}/{den}*{self.multiplier}),"")'


RATIOS = [
    Ratio("current_ratio", "Current ratio", "Current", "Liquidity",
          [("current_assets", 1)], [("current_liabilities", 1)], True, 1.2, 0.9, "x",
          action="Build a liquidity buffer: renegotiate supplier terms or add a working-capital line."),
    Ratio("quick_ratio", "Quick ratio", "Quick", "Liquidity",
          [("current_assets", 1), ("inventory", -1)], [("current_liabilities", 1)], True, 0.8, 0.5, "x",
          action="Liquidity leans on inventory; speed up cash collection before committing to new capex."),
    Ratio("debt_to_equity", "Debt / equity", "D/E", "Solvency",
          [("total_debt", 1)], [("equity", 1)], False, 0.5, 1.0, "x",
          action="Pause debt-funded expansion until leverage is back inside the green band."),
    Ratio("interest_coverage", "Interest coverage", "Int. cover", "Solvency",
          [("ebit", 1)], [("interest", 1)], True, 5.0, 2.5, "x",
          action="Earnings cover interest thinly; refinance costly debt or prepay loans."),
    Ratio("net_debt_to_ebitda", "Net debt / EBITDA", "ND/EBITDA", "Solvency",
          [("total_debt", 1), ("cash", -1)], [("ebitda", 1)], False, 1.5, 3.0, "x",
          action="Lenders should watch covenants; direct free cash flow to deleveraging."),
    Ratio("ebitda_margin", "EBITDA margin", "EBITDA %", "Profitability",
          [("ebitda", 1)], [("revenue", 1)], True, 0.18, 0.12, "%",
          action="Operating margin trails peers; review input-cost contracts and pricing power."),
    Ratio("net_margin", "Net profit margin", "Net %", "Profitability",
          [("net_income", 1)], [("revenue", 1)], True, 0.10, 0.05, "%",
          action="Bottom-line margin is thin; check whether interest or depreciation is the drag."),
    Ratio("roe", "Return on equity", "ROE", "Profitability",
          [("net_income", 1)], [("equity", 1)], True, 0.15, 0.10, "%",
          action="Shareholder returns are low; test capital allocation (expansion vs dividends or buybacks)."),
    Ratio("roa", "Return on assets", "ROA", "Profitability",
          [("net_income", 1)], [("total_assets", 1)], True, 0.08, 0.04, "%",
          action="The asset base earns little; prune idle assets or lift utilisation."),
    Ratio("roce", "Return on capital employed", "ROCE", "Profitability",
          [("ebit", 1)], [("equity", 1), ("total_debt", 1)], True, 0.15, 0.10, "%",
          action="Capital is not earning its cost; slow new capex until existing assets pay back."),
    Ratio("asset_turnover", "Asset turnover", "Asset turn", "Efficiency",
          [("revenue", 1)], [("total_assets", 1)], True, 0.8, 0.5, "x",
          action="Assets generate little revenue; sweat existing capacity before adding more."),
    Ratio("receivable_days", "Receivable days", "Debtor days", "Efficiency",
          [("receivables", 1)], [("revenue", 1)], False, 45, 75, "days", multiplier=365,
          action="Customers are paying slowly; tighten credit terms and collections."),
]
RATIO_BY_KEY = {r.key: r for r in RATIOS}
STATUS_POINTS = {"Green": 2, "Amber": 1, "Red": 0}


class RatioEngine:
    def __init__(self, ratios=RATIOS):
        self.ratios = ratios

    def compute_all(self, data):
        result = data[["company", "symbol", "year"]].copy()
        for ratio in self.ratios:
            result[ratio.key] = ratio.compute(data) if len(data) else []
        return result

    def available(self, ratio_values):
        """Ratios with at least one number for this peer set (bank accounts have no current ratio)."""
        return [r for r in self.ratios if ratio_values[r.key].notna().any()]

    def rag_table(self, ratio_values):
        rag = ratio_values[["company", "symbol", "year"]].copy()
        for ratio in self.ratios:
            rag[ratio.key] = ratio_values[ratio.key].apply(ratio.rate)
        return rag

    def health_scores(self, rag):
        """0-100: Green = 2 points, Amber = 1, Red = 0; n/a ratios are left out rather than penalised."""
        points = rag[[r.key for r in self.ratios]].apply(lambda col: col.map(STATUS_POINTS))
        scores = rag[["company", "symbol", "year"]].copy()
        scores["health_score"] = (points.mean(axis=1) / 2 * 100).round(1)
        return scores

    def peer_percentiles(self, ratio_values, year):
        """0-100 rank of each company on each ratio within the peer set (100 = best)."""
        snapshot = ratio_values[ratio_values.year == year].set_index("company")
        result = pd.DataFrame(index=snapshot.index)
        for ratio in self.ratios:
            ranks = snapshot[ratio.key].rank(pct=True, ascending=ratio.higher_is_better)
            result[ratio.key] = (ranks * 100).round(0)
        return result

    def trend_flags(self, ratio_values, lookback=3, threshold=0.10):
        """Latest year against the average of the previous `lookback` years, per company and ratio."""
        records = []
        for company, group in ratio_values.groupby("company"):
            group = group.sort_values("year")
            latest = group.iloc[-1]
            history = group.iloc[:-1].tail(lookback)
            for ratio in self.ratios:
                now, before = latest[ratio.key], history[ratio.key].mean() if len(history) else np.nan
                change = np.nan if (pd.isna(now) or pd.isna(before) or before == 0) else (now - before) / abs(before)
                if pd.isna(change):
                    worse = False
                else:
                    worse = change < -threshold if ratio.higher_is_better else change > threshold
                records.append(dict(company=company, ratio=ratio.key, year=latest["year"], latest=now,
                                    prior_avg=before, change_pct=change, deteriorating=bool(worse)))
        return pd.DataFrame(records)


def latest_common_year(ratio_values):
    """Most recent year that every company reports; falls back to the overall latest year."""
    years_per_company = ratio_values.groupby("company")["year"].apply(set)
    common = set.intersection(*years_per_company) if len(years_per_company) else set()
    return max(common) if common else ratio_values["year"].max()


def build_recommendations(company, year, ratio_values, rag, trends, ratios=RATIOS, max_items=3):
    """Rank a company's weak spots. Severity: Red = 2, worsening trend = 1, Amber and behind peers = 0.5."""
    row = ratio_values[(ratio_values.company == company) & (ratio_values.year == year)]
    if row.empty:
        return [dict(status="n/a", ratio="—", text=f"No {year} data for {company}.")]
    row = row.iloc[0]
    status_row = rag[(rag.company == company) & (rag.year == year)].iloc[0]
    snapshot = ratio_values[ratio_values.year == year]
    # the benchmark is the other peers; a median that includes the company itself flatters or hides gaps
    peer_median = snapshot[snapshot.company != company][[r.key for r in ratios]].median()
    company_trends = trends[trends.company == company].set_index("ratio")

    findings = []
    for ratio in ratios:
        value, status, median = row[ratio.key], status_row[ratio.key], peer_median[ratio.key]
        if pd.isna(value):
            continue
        worsening = bool(company_trends.loc[ratio.key, "deteriorating"]) if ratio.key in company_trends.index else False
        behind = pd.notna(median) and (value < median if ratio.higher_is_better else value > median)
        worsening = worsening and status != "Green"   # a slipping but still-green ratio is not an action item
        severity = 2 * (status == "Red") + 1 * worsening + 0.5 * (status == "Amber" and behind)
        if severity > 0:
            change = company_trends.loc[ratio.key, "change_pct"] if ratio.key in company_trends.index else np.nan
            trend_text = f", {change:+.0%} vs its 3-year average" if worsening and pd.notna(change) else ""
            findings.append((severity, dict(
                status=status + (", worsening" if worsening else ""), ratio=ratio.name,
                text=f"{ratio.format(value)} against a peer median of {ratio.format(median)}{trend_text}. "
                     f"{ratio.action}")))
    findings.sort(key=lambda item: item[0], reverse=True)
    if not findings:
        return [dict(status="Green", ratio="All clear",
                     text="No red, worsening or lagging ratios. Hold strategy and re-check next quarter.")]
    return [f[1] for f in findings[:max_items]]


def strengths(company, year, ratio_values, ratios=RATIOS, max_items=3, exclude=()):
    """Ratios where the company leads the other peers by the widest margin. Ratios already flagged as
    findings (`exclude`, by name) are left out so a ratio is never both a strength and a problem."""
    snapshot = ratio_values[ratio_values.year == year]
    row = snapshot[snapshot.company == company]
    if row.empty or len(snapshot) < 2:
        return []
    row = row.iloc[0]
    others = snapshot[snapshot.company != company]
    edges = []
    for ratio in ratios:
        value, median = row[ratio.key], others[ratio.key].median()
        if pd.isna(value) or pd.isna(median) or median == 0 or ratio.name in exclude:
            continue
        edge = (value - median) / abs(median) * (1 if ratio.higher_is_better else -1)
        if edge > 0.05:
            edges.append((edge, f"{ratio.name} {ratio.format(value)} (peers {ratio.format(median)})"))
    return [text for _, text in sorted(edges, reverse=True)[:max_items]]
