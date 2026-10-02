"""Audits financial data before any ratio is trusted.

Two modes, because the right fix depends on where the data came from:
  * synthetic: the generator guarantees Assets = Equity + Debt + Current liabilities, so a single
    missing balance-sheet item can be rebuilt exactly and sign errors can be corrected.
  * live: real accounts have other liabilities too, so the identity cannot be enforced and values are
    never invented. Problems are flagged and the affected ratios show as n/a.
"""
import numpy as np
import pandas as pd

from .schema import ABSENT_MEANS_ZERO, ALL_COLUMNS, CORE_ITEMS, NON_NEGATIVE

IDENTITY_ASSETS = ["total_assets"]
IDENTITY_FUNDING = ["equity", "total_debt", "current_liabilities"]
REBUILDABLE = ["inventory", "receivables", "cash"]


class FinancialDataValidator:
    def __init__(self, mode="live", tolerance=1.0):
        if mode not in ("live", "synthetic"):
            raise ValueError("mode must be 'live' or 'synthetic'")
        self.mode = mode
        self.tolerance = tolerance     # ₹ crore allowed for rounding differences

    @staticmethod
    def check_columns(data):
        missing = [c for c in ALL_COLUMNS if c not in data.columns]
        if missing:
            raise ValueError(f"Input data is missing required columns: {missing}")

    def validate(self, data):
        """Return a table of issues: severity, company, year, check, detail."""
        self.check_columns(data)
        issues = []

        def add(severity, row, check, detail):
            issues.append((severity, row["company"], row["year"], check, detail))

        for _, row in data[data.duplicated(["symbol", "year"], keep="first")].iterrows():
            add("Warning", row, "Duplicate row", "Same company and year appears twice")

        for col in NON_NEGATIVE:
            for _, row in data[data[col] < 0].iterrows():
                add("Critical", row, "Negative value", f"{col} = {row[col]:,.1f}")

        for col in CORE_ITEMS:
            for _, row in data[data[col].isna()].iterrows():
                add("Critical", row, "Missing core item", f"{col} is blank; ratios using it show n/a")

        if self.mode == "synthetic":
            for col in REBUILDABLE:
                for _, row in data[data[col].isna()].iterrows():
                    add("Critical", row, "Missing value", f"{col} is blank")
            parts = data.dropna(subset=REBUILDABLE + ["current_assets"])
            sub_gap = parts["current_assets"] - parts[REBUILDABLE].sum(axis=1)
            for idx in sub_gap[sub_gap.abs() > self.tolerance].index:
                add("Critical", data.loc[idx], "Sub-total mismatch",
                    f"Current assets differ from inventory + receivables + cash by ₹{abs(sub_gap[idx]):,.1f} cr")
            complete = data.dropna(subset=IDENTITY_ASSETS + IDENTITY_FUNDING)
            gap = complete["total_assets"] - complete[IDENTITY_FUNDING].sum(axis=1)
            for idx in gap[gap.abs() > self.tolerance].index:
                add("Critical", data.loc[idx], "Balance sheet mismatch",
                    f"Assets and funding differ by ₹{abs(gap[idx]):,.1f} cr")
        else:
            for _, row in data[data["equity"] < 0].iterrows():
                add("Warning", row, "Negative equity", "Accumulated losses exceed capital; ROE is not meaningful")

        latest = data.groupby("company")["year"].max()
        newest = data["year"].max() if len(data) else None
        for company, year in latest.items():
            if newest and int(year[2:]) < int(newest[2:]) - 1:
                issues.append(("Warning", company, year, "Stale data",
                               f"Latest statement is {year}; peers report up to {newest}"))
        for company, count in data.groupby("company")["year"].nunique().items():
            if count < 2:
                issues.append(("Warning", company, "-", "Short history", "Fewer than 2 years; trends show n/a"))

        return pd.DataFrame(issues, columns=["severity", "company", "year", "check", "detail"])

    def clean(self, data):
        """Apply only the fixes that are safe for this mode. Returns (clean_data, fix_log)."""
        self.check_columns(data)
        data = data.copy()
        fixes = []

        before = len(data)
        data = data.drop_duplicates(["symbol", "year"], keep="first").reset_index(drop=True)
        if len(data) < before:
            fixes.append(("Removed duplicates", f"{before - len(data)} duplicate row(s) dropped"))

        if self.mode == "live":
            for col in ABSENT_MEANS_ZERO:
                blank = data[col].isna() & data["revenue"].notna()
                if blank.any():
                    fixes.append(("Absent item set to 0",
                                  f"{col}: {blank.sum()} row(s) where Yahoo reports no line item "
                                  f"(e.g. no inventory for a services firm)"))
                data.loc[blank, col] = 0.0
            return data, pd.DataFrame(fixes, columns=["action", "detail"])

        # ---- synthetic mode: stronger, provably-correct repairs ----
        for col in NON_NEGATIVE:
            negative = data[col] < 0
            for idx in data[negative].index:
                fixes.append(("Sign corrected", f"{data.at[idx, 'company']} {data.at[idx, 'year']}: "
                                                f"{col} {data.at[idx, col]:,.1f} → {abs(data.at[idx, col]):,.1f}"))
            data.loc[negative, col] = data.loc[negative, col].abs()

        for idx, row in data.iterrows():
            missing = [c for c in REBUILDABLE if pd.isna(row[c])]
            if len(missing) == 1:
                item = missing[0]
                others = sum(row[c] for c in REBUILDABLE if c != item)
                if pd.isna(row["current_assets"]):
                    fixes.append(("Left blank", f"{row['company']} {row['year']}: {item} (no sub-total to rebuild from)"))
                    continue
                # Current assets = inventory + receivables + cash, so the missing piece is the gap
                value = round(row["current_assets"] - others, 1)
                data.at[idx, item] = value
                fixes.append(("Rebuilt from identity", f"{row['company']} {row['year']}: {item} = {value:,.1f}"))

        return data, pd.DataFrame(fixes, columns=["action", "detail"])


def fill_absent_for_excel(data):
    """Excel treats blank cells as zero; keep NaN as None so blanks stay blank."""
    return data.replace({np.nan: None})
