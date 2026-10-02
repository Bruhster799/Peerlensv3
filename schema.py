"""The one table format every data source is converted into (₹ crore)."""

ID_COLUMNS = ["company", "symbol", "year"]

INCOME_ITEMS = ["revenue", "ebitda", "ebit", "depreciation", "interest", "pretax_income", "tax",
                "net_income"]
BALANCE_ITEMS = ["total_assets", "current_assets", "current_liabilities", "inventory", "receivables",
                 "cash", "total_debt", "equity"]
FINANCIAL_COLUMNS = INCOME_ITEMS + BALANCE_ITEMS
ALL_COLUMNS = ID_COLUMNS + FINANCIAL_COLUMNS

# Items that cannot be negative in a sensible set of accounts
NON_NEGATIVE = ["revenue", "depreciation", "interest", "total_assets", "current_assets",
                "current_liabilities", "inventory", "receivables", "cash", "total_debt"]

# Items a company can genuinely not have (an IT firm has no inventory, a debt-free firm no debt)
ABSENT_MEANS_ZERO = ["inventory", "total_debt", "interest"]

# Without these, most ratios are meaningless
CORE_ITEMS = ["revenue", "net_income", "total_assets", "equity"]

LABELS = {
    "revenue": "Revenue", "ebitda": "EBITDA", "ebit": "EBIT", "depreciation": "Depreciation",
    "interest": "Interest expense", "pretax_income": "Profit before tax", "tax": "Tax",
    "net_income": "Net profit", "total_assets": "Total assets", "current_assets": "Current assets",
    "current_liabilities": "Current liabilities", "inventory": "Inventory",
    "receivables": "Receivables", "cash": "Cash", "total_debt": "Total debt", "equity": "Equity",
}


def fiscal_year_label(timestamp):
    """Indian financial years end in March: a period ending Mar-2025 is FY2025, Dec-2024 is FY2025."""
    return f"FY{timestamp.year if timestamp.month <= 3 else timestamp.year + 1}"
