"""Account grouping maps and standard line-item hierarchies for GAAP statements."""

from __future__ import annotations

STATEMENT_BALANCE_SHEET = "Balance Sheet"
STATEMENT_INCOME = "Income Statement"
STATEMENT_CASH_FLOW = "Cash Flow Statement"
STATEMENT_EQUITY = "Statement of Changes in Equity"
STATEMENT_ACTIVITIES = "Statement of Activities"
STATEMENT_FINANCIAL_POSITION = "Statement of Financial Position"
STATEMENT_FUNCTIONAL_EXPENSES = "Statement of Functional Expenses"

ENTITY_FOR_PROFIT = "For-Profit"
ENTITY_NONPROFIT = "Nonprofit (ASC 958)"


# Account number prefix → standard GAAP line-item heuristics. These are
# fallbacks used when the user's TB has no grouping column and Claude is not
# available; they cover the common chart-of-accounts numbering convention.
ACCOUNT_NUMBER_PREFIX_MAP = {
    "1": ("Assets", STATEMENT_BALANCE_SHEET),
    "2": ("Liabilities", STATEMENT_BALANCE_SHEET),
    "3": ("Equity", STATEMENT_BALANCE_SHEET),
    "4": ("Revenue", STATEMENT_INCOME),
    "5": ("Cost of Goods Sold", STATEMENT_INCOME),
    "6": ("Operating Expenses", STATEMENT_INCOME),
    "7": ("Operating Expenses", STATEMENT_INCOME),
    "8": ("Other Income/Expense", STATEMENT_INCOME),
    "9": ("Income Tax", STATEMENT_INCOME),
}


# Standard GAAP balance sheet structure (for-profit). Each row is
# (line_item, level, kind) where kind is one of: line, subtotal, total, header.
BALANCE_SHEET_STRUCTURE_FOR_PROFIT = [
    ("ASSETS", 0, "header"),
    ("Current Assets", 1, "header"),
    ("Cash and cash equivalents", 2, "line"),
    ("Accounts receivable, net", 2, "line"),
    ("Inventory", 2, "line"),
    ("Prepaid expenses", 2, "line"),
    ("Other current assets", 2, "line"),
    ("Total current assets", 1, "subtotal"),
    ("Property, plant and equipment, net", 1, "line"),
    ("Intangible assets, net", 1, "line"),
    ("Goodwill", 1, "line"),
    ("Other assets", 1, "line"),
    ("Total assets", 0, "total"),
    ("LIABILITIES AND STOCKHOLDERS' EQUITY", 0, "header"),
    ("Current Liabilities", 1, "header"),
    ("Accounts payable", 2, "line"),
    ("Accrued expenses", 2, "line"),
    ("Deferred revenue, current", 2, "line"),
    ("Current portion of long-term debt", 2, "line"),
    ("Other current liabilities", 2, "line"),
    ("Total current liabilities", 1, "subtotal"),
    ("Long-term debt, net of current portion", 1, "line"),
    ("Deferred tax liabilities", 1, "line"),
    ("Other long-term liabilities", 1, "line"),
    ("Total liabilities", 0, "subtotal"),
    ("Stockholders' Equity", 1, "header"),
    ("Common stock", 2, "line"),
    ("Additional paid-in capital", 2, "line"),
    ("Retained earnings", 2, "line"),
    ("Accumulated other comprehensive income (loss)", 2, "line"),
    ("Total stockholders' equity", 1, "subtotal"),
    ("Total liabilities and stockholders' equity", 0, "total"),
]


# Statement of Financial Position (nonprofit) — ASC 958.
BALANCE_SHEET_STRUCTURE_NONPROFIT = [
    ("ASSETS", 0, "header"),
    ("Cash and cash equivalents", 1, "line"),
    ("Contributions receivable, net", 1, "line"),
    ("Accounts receivable, net", 1, "line"),
    ("Investments", 1, "line"),
    ("Prepaid expenses and other assets", 1, "line"),
    ("Property and equipment, net", 1, "line"),
    ("Total assets", 0, "total"),
    ("LIABILITIES AND NET ASSETS", 0, "header"),
    ("Liabilities", 1, "header"),
    ("Accounts payable and accrued expenses", 2, "line"),
    ("Deferred revenue", 2, "line"),
    ("Notes payable", 2, "line"),
    ("Total liabilities", 1, "subtotal"),
    ("Net Assets", 1, "header"),
    ("Without donor restrictions", 2, "line"),
    ("With donor restrictions", 2, "line"),
    ("Total net assets", 1, "subtotal"),
    ("Total liabilities and net assets", 0, "total"),
]


INCOME_STATEMENT_STRUCTURE = [
    ("Revenue", 0, "line"),
    ("Cost of revenue", 0, "line"),
    ("Gross profit", 0, "subtotal"),
    ("Operating Expenses", 0, "header"),
    ("Selling, general and administrative", 1, "line"),
    ("Research and development", 1, "line"),
    ("Depreciation and amortization", 1, "line"),
    ("Total operating expenses", 0, "subtotal"),
    ("Operating income (loss)", 0, "subtotal"),
    ("Other Income (Expense)", 0, "header"),
    ("Interest income", 1, "line"),
    ("Interest expense", 1, "line"),
    ("Other, net", 1, "line"),
    ("Total other income (expense), net", 0, "subtotal"),
    ("Income (loss) before income taxes", 0, "subtotal"),
    ("Provision for (benefit from) income taxes", 0, "line"),
    ("Net income (loss)", 0, "total"),
]


STATEMENT_OF_ACTIVITIES_STRUCTURE = [
    ("REVENUES, GAINS, AND OTHER SUPPORT", 0, "header"),
    ("Contributions", 1, "line"),
    ("Grants", 1, "line"),
    ("Program service fees", 1, "line"),
    ("Investment income, net", 1, "line"),
    ("Other income", 1, "line"),
    ("Net assets released from restrictions", 1, "line"),
    ("Total revenues, gains, and other support", 0, "subtotal"),
    ("EXPENSES", 0, "header"),
    ("Program services", 1, "line"),
    ("Management and general", 1, "line"),
    ("Fundraising", 1, "line"),
    ("Total expenses", 0, "subtotal"),
    ("Change in net assets", 0, "subtotal"),
    ("Net assets, beginning of year", 0, "line"),
    ("Net assets, end of year", 0, "total"),
]


CASH_FLOW_INDIRECT_STRUCTURE = [
    ("CASH FLOWS FROM OPERATING ACTIVITIES", 0, "header"),
    ("Net income (loss)", 1, "line"),
    ("Adjustments to reconcile net income to net cash:", 1, "header"),
    ("Depreciation and amortization", 2, "line"),
    ("Stock-based compensation", 2, "line"),
    ("Deferred income taxes", 2, "line"),
    ("Changes in operating assets and liabilities:", 1, "header"),
    ("Accounts receivable", 2, "line"),
    ("Inventory", 2, "line"),
    ("Prepaid expenses", 2, "line"),
    ("Accounts payable", 2, "line"),
    ("Accrued expenses", 2, "line"),
    ("Deferred revenue", 2, "line"),
    ("Net cash provided by (used in) operating activities", 0, "subtotal"),
    ("CASH FLOWS FROM INVESTING ACTIVITIES", 0, "header"),
    ("Purchases of property and equipment", 1, "line"),
    ("Purchases of investments", 1, "line"),
    ("Proceeds from sale of investments", 1, "line"),
    ("Net cash provided by (used in) investing activities", 0, "subtotal"),
    ("CASH FLOWS FROM FINANCING ACTIVITIES", 0, "header"),
    ("Proceeds from issuance of debt", 1, "line"),
    ("Repayments of debt", 1, "line"),
    ("Proceeds from issuance of stock", 1, "line"),
    ("Dividends paid", 1, "line"),
    ("Net cash provided by (used in) financing activities", 0, "subtotal"),
    ("Net change in cash and cash equivalents", 0, "subtotal"),
    ("Cash and cash equivalents, beginning of period", 0, "line"),
    ("Cash and cash equivalents, end of period", 0, "total"),
]


CASH_FLOW_DIRECT_STRUCTURE = [
    ("CASH FLOWS FROM OPERATING ACTIVITIES", 0, "header"),
    ("Cash received from customers", 1, "line"),
    ("Cash paid to suppliers and employees", 1, "line"),
    ("Interest paid", 1, "line"),
    ("Income taxes paid", 1, "line"),
    ("Net cash provided by (used in) operating activities", 0, "subtotal"),
    ("CASH FLOWS FROM INVESTING ACTIVITIES", 0, "header"),
    ("Purchases of property and equipment", 1, "line"),
    ("Purchases of investments", 1, "line"),
    ("Proceeds from sale of investments", 1, "line"),
    ("Net cash provided by (used in) investing activities", 0, "subtotal"),
    ("CASH FLOWS FROM FINANCING ACTIVITIES", 0, "header"),
    ("Proceeds from issuance of debt", 1, "line"),
    ("Repayments of debt", 1, "line"),
    ("Proceeds from issuance of stock", 1, "line"),
    ("Dividends paid", 1, "line"),
    ("Net cash provided by (used in) financing activities", 0, "subtotal"),
    ("Net change in cash and cash equivalents", 0, "subtotal"),
    ("Cash and cash equivalents, beginning of period", 0, "line"),
    ("Cash and cash equivalents, end of period", 0, "total"),
]


CHANGES_IN_EQUITY_STRUCTURE = [
    ("Balance, beginning of year", 0, "line"),
    ("Net income (loss)", 0, "line"),
    ("Issuance of common stock", 0, "line"),
    ("Stock-based compensation", 0, "line"),
    ("Dividends declared", 0, "line"),
    ("Other comprehensive income (loss)", 0, "line"),
    ("Balance, end of year", 0, "total"),
]


FUNCTIONAL_EXPENSES_PROGRAMS = ["Program A", "Program B", "Management & General", "Fundraising"]
FUNCTIONAL_EXPENSES_CATEGORIES = [
    "Salaries and wages",
    "Employee benefits",
    "Payroll taxes",
    "Professional fees",
    "Occupancy",
    "Office expenses",
    "Information technology",
    "Travel",
    "Conferences and meetings",
    "Depreciation",
    "Other expenses",
]


def get_statement_structure(statement_name: str, entity_type: str, cash_flow_method: str = "Indirect"):
    """Return the standard line-item template for a given statement."""
    if statement_name in (STATEMENT_BALANCE_SHEET, STATEMENT_FINANCIAL_POSITION):
        if entity_type == ENTITY_NONPROFIT:
            return BALANCE_SHEET_STRUCTURE_NONPROFIT
        return BALANCE_SHEET_STRUCTURE_FOR_PROFIT
    if statement_name == STATEMENT_INCOME:
        return INCOME_STATEMENT_STRUCTURE
    if statement_name == STATEMENT_ACTIVITIES:
        return STATEMENT_OF_ACTIVITIES_STRUCTURE
    if statement_name == STATEMENT_CASH_FLOW:
        return CASH_FLOW_DIRECT_STRUCTURE if cash_flow_method == "Direct" else CASH_FLOW_INDIRECT_STRUCTURE
    if statement_name == STATEMENT_EQUITY:
        return CHANGES_IN_EQUITY_STRUCTURE
    return []


def keyword_to_line_item(description: str, entity_type: str = ENTITY_FOR_PROFIT) -> str:
    """Heuristic match from an account description to a standard GAAP line item."""
    desc = (description or "").lower()
    rules = [
        (["cash", "checking", "savings", "money market"], "Cash and cash equivalents"),
        (["account receivable", "accounts receivable", "a/r", "trade receivable"], "Accounts receivable, net"),
        (["contribution receivable", "pledges receivable"], "Contributions receivable, net"),
        (["inventory", "stock on hand"], "Inventory"),
        (["prepaid"], "Prepaid expenses"),
        (["building", "equipment", "machinery", "furniture", "vehicle", "leasehold improve"], "Property, plant and equipment, net"),
        (["accumulated depreciation"], "Property, plant and equipment, net"),
        (["goodwill"], "Goodwill"),
        (["intangible", "patent", "trademark", "software"], "Intangible assets, net"),
        (["account payable", "accounts payable", "a/p", "trade payable"], "Accounts payable"),
        (["accrued"], "Accrued expenses"),
        (["deferred revenue", "unearned revenue"], "Deferred revenue, current"),
        (["note payable", "loan payable", "line of credit"], "Long-term debt, net of current portion"),
        (["common stock", "capital stock"], "Common stock"),
        (["paid-in capital", "additional paid"], "Additional paid-in capital"),
        (["retained earnings"], "Retained earnings"),
        (["without donor restriction", "unrestricted"], "Without donor restrictions"),
        (["with donor restriction", "temporarily restricted", "permanently restricted"], "With donor restrictions"),
        (["sales", "revenue", "service revenue"], "Revenue"),
        (["contribution income", "donation"], "Contributions"),
        (["grant"], "Grants"),
        (["cost of goods sold", "cost of sales", "cogs"], "Cost of revenue"),
        (["salary", "wages", "payroll"], "Selling, general and administrative"),
        (["rent"], "Selling, general and administrative"),
        (["depreciation expense"], "Depreciation and amortization"),
        (["interest expense"], "Interest expense"),
        (["interest income"], "Interest income"),
        (["income tax", "tax expense", "provision for tax"], "Provision for (benefit from) income taxes"),
    ]
    for keywords, line_item in rules:
        for keyword in keywords:
            if keyword in desc:
                return line_item
    return "Uncategorized"
