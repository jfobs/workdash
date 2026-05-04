"""GAAP disclosure checklist rules engine.

Each rule has:
- id: stable identifier
- title: user-facing label
- category: grouping (e.g., "Accounting Policies", "Debt", "Net Assets")
- default_status: "Required" | "Recommended" | "N/A"
- predicate: callable(facts: dict) -> bool — when True, the item is triggered

The page renders the full set of triggered rules; users can override Required/N/A.
"""

from __future__ import annotations

from typing import Callable

from utils.mappings import ENTITY_FOR_PROFIT, ENTITY_NONPROFIT


REQUIRED = "Required"
RECOMMENDED = "Recommended"
NA = "N/A"


CATEGORIES = [
    "Accounting Policies",
    "Cash and Receivables",
    "Inventory",
    "Property and Equipment",
    "Intangibles and Goodwill",
    "Investments and Fair Value",
    "Debt",
    "Leases",
    "Income Taxes",
    "Revenue",
    "Net Assets",
    "Functional Expenses",
    "Compensation and Benefits",
    "Commitments and Contingencies",
    "Related Party",
    "Subsequent Events",
    "Risks and Uncertainties",
]


def _has_balance(facts: dict, line_keywords: list[str], threshold: float = 0.0) -> bool:
    summary = facts.get("statements_summary", {}) or {}
    for stmt_lines in summary.values():
        if not isinstance(stmt_lines, list):
            continue
        for row in stmt_lines:
            line = str(row.get("line_item", "")).lower()
            cy = abs(float(row.get("cy_balance", 0) or 0))
            py = abs(float(row.get("py_balance", 0) or 0))
            if any(kw in line for kw in line_keywords) and (cy > threshold or py > threshold):
                return True
    return False


def _is_nonprofit(facts: dict) -> bool:
    return facts.get("entity_type") == ENTITY_NONPROFIT


def _is_for_profit(facts: dict) -> bool:
    return facts.get("entity_type") == ENTITY_FOR_PROFIT


def _statements_include(facts: dict, name: str) -> bool:
    selected = facts.get("statements_selected", []) or []
    return any(name.lower() in str(s).lower() for s in selected)


# Rule definitions: (id, title, category, default_status, predicate)
RULES: list[tuple[str, str, str, str, Callable[[dict], bool]]] = [
    ("note_01_sigacct", "Summary of Significant Accounting Policies",
     "Accounting Policies", REQUIRED, lambda f: True),
    ("note_org_nature", "Nature of Operations / Organization",
     "Accounting Policies", REQUIRED, lambda f: True),
    ("note_basis", "Basis of Presentation",
     "Accounting Policies", REQUIRED, lambda f: True),
    ("note_estimates", "Use of Estimates",
     "Accounting Policies", REQUIRED, lambda f: True),
    ("note_concentrations", "Concentrations of Credit Risk",
     "Risks and Uncertainties", RECOMMENDED, lambda f: True),
    ("note_cash", "Cash and Cash Equivalents",
     "Cash and Receivables", REQUIRED,
     lambda f: _has_balance(f, ["cash"])),
    ("note_ar", "Accounts Receivable and Allowance for Credit Losses (CECL, ASC 326)",
     "Cash and Receivables", REQUIRED,
     lambda f: _has_balance(f, ["receivable"])),
    ("note_inventory", "Inventory",
     "Inventory", REQUIRED,
     lambda f: _has_balance(f, ["inventory"])),
    ("note_ppe", "Property, Plant and Equipment (or Property and Equipment)",
     "Property and Equipment", REQUIRED,
     lambda f: _has_balance(f, ["property", "equipment", "plant"])),
    ("note_intangibles", "Intangible Assets",
     "Intangibles and Goodwill", REQUIRED,
     lambda f: _has_balance(f, ["intangible", "patent", "trademark"])),
    ("note_goodwill", "Goodwill (ASC 350)",
     "Intangibles and Goodwill", REQUIRED,
     lambda f: _has_balance(f, ["goodwill"])),
    ("note_investments", "Investments and Fair Value Measurements (ASC 820)",
     "Investments and Fair Value", REQUIRED,
     lambda f: _has_balance(f, ["investment"])),
    ("note_debt", "Long-Term Debt",
     "Debt", REQUIRED,
     lambda f: _has_balance(f, ["debt", "note payable", "loan", "bond"])),
    ("note_leases", "Leases (ASC 842)",
     "Leases", REQUIRED,
     lambda f: bool(f.get("has_leases"))),
    ("note_income_taxes", "Income Taxes (ASC 740)",
     "Income Taxes", REQUIRED,
     lambda f: _is_for_profit(f) and (_has_balance(f, ["income tax", "tax"]) or bool(f.get("has_income_taxes")))),
    ("note_revenue", "Revenue Recognition (ASC 606)",
     "Revenue", REQUIRED,
     lambda f: _is_for_profit(f) and _has_balance(f, ["revenue", "sales"])),
    ("note_net_assets", "Net Assets (ASC 958)",
     "Net Assets", REQUIRED,
     lambda f: _is_nonprofit(f)),
    ("note_donor_restrictions", "Donor Restrictions and Releases",
     "Net Assets", REQUIRED,
     lambda f: _is_nonprofit(f) and _has_balance(f, ["restriction"])),
    ("note_liquidity", "Liquidity and Availability of Resources (ASC 958-210-50)",
     "Net Assets", REQUIRED,
     lambda f: _is_nonprofit(f)),
    ("note_functional_expenses", "Functional Expenses Allocation",
     "Functional Expenses", REQUIRED,
     lambda f: _is_nonprofit(f) or _statements_include(f, "Functional Expenses")),
    ("note_contributions", "Contributions and Revenue Recognition (ASC 958-605, ASC 606)",
     "Revenue", REQUIRED,
     lambda f: _is_nonprofit(f)),
    ("note_endowment", "Endowment Funds and UPMIFA Disclosures",
     "Net Assets", RECOMMENDED,
     lambda f: _is_nonprofit(f) and _has_balance(f, ["endowment"])),
    ("note_employee_benefits", "Employee Benefit Plans",
     "Compensation and Benefits", RECOMMENDED,
     lambda f: bool(f.get("has_benefit_plans"))),
    ("note_stock_based_comp", "Stock-Based Compensation (ASC 718)",
     "Compensation and Benefits", REQUIRED,
     lambda f: _is_for_profit(f) and bool(f.get("has_stock_comp"))),
    ("note_equity", "Stockholders' Equity",
     "Net Assets", REQUIRED,
     lambda f: _is_for_profit(f)),
    ("note_commitments", "Commitments and Contingencies",
     "Commitments and Contingencies", REQUIRED, lambda f: True),
    ("note_related_party", "Related Party Transactions",
     "Related Party", RECOMMENDED, lambda f: True),
    ("note_subsequent", "Subsequent Events",
     "Subsequent Events", REQUIRED, lambda f: True),
    ("note_risks", "Risks and Uncertainties (ASC 275)",
     "Risks and Uncertainties", REQUIRED, lambda f: True),
    ("note_recent_pronouncements", "Recent Accounting Pronouncements",
     "Accounting Policies", RECOMMENDED, lambda f: True),
]


def build_checklist(facts: dict) -> list[dict]:
    """Build the checklist for the current session.

    facts keys:
      - entity_type: "For-Profit" | "Nonprofit (ASC 958)"
      - statements_selected: list[str]
      - statements_summary: dict[statement_name -> list[{line_item, cy_balance, py_balance}]]
      - has_leases: bool (optional)
      - has_income_taxes: bool (optional)
      - has_stock_comp: bool (optional)
      - has_benefit_plans: bool (optional)
    """
    items: list[dict] = []
    for rule_id, title, category, default_status, predicate in RULES:
        try:
            triggered = bool(predicate(facts))
        except Exception:
            triggered = False
        # Items not triggered are still shown but defaulted to N/A so users can
        # opt-in if they know they need them.
        status = default_status if triggered else NA
        items.append({
            "id": rule_id,
            "title": title,
            "category": category,
            "status": status,
            "complete": False,
            "default_status": default_status,
            "auto_triggered": triggered,
        })
    return items


def merge_checklist(existing: list[dict], rebuilt: list[dict]) -> list[dict]:
    """Re-run rules without losing user overrides on existing items."""
    by_id = {item["id"]: item for item in (existing or [])}
    merged = []
    for item in rebuilt:
        prior = by_id.get(item["id"])
        if prior:
            item = dict(item)
            item["status"] = prior.get("status", item["status"])
            item["complete"] = prior.get("complete", item["complete"])
        merged.append(item)
    return merged


def progress(checklist: list[dict]) -> tuple[int, int]:
    """Return (completed_required_count, total_required_count)."""
    required = [c for c in (checklist or []) if c.get("status") == REQUIRED]
    completed = [c for c in required if c.get("complete")]
    return len(completed), len(required)


def required_note_titles(checklist: list[dict]) -> list[str]:
    """Note titles that should be drafted by the AI engine."""
    return [c["title"] for c in (checklist or []) if c.get("status") in (REQUIRED, RECOMMENDED)]


# Standard catalog used in the "Add Note" dropdown on Page 3.
STANDARD_NOTE_CATALOG = [
    "Summary of Significant Accounting Policies",
    "Nature of Operations / Organization",
    "Cash and Cash Equivalents",
    "Accounts Receivable",
    "Allowance for Credit Losses (CECL, ASC 326)",
    "Inventory",
    "Property, Plant and Equipment",
    "Intangible Assets",
    "Goodwill (ASC 350)",
    "Investments and Fair Value Measurements (ASC 820)",
    "Long-Term Debt",
    "Leases (ASC 842)",
    "Income Taxes (ASC 740)",
    "Revenue Recognition (ASC 606)",
    "Stock-Based Compensation (ASC 718)",
    "Stockholders' Equity",
    "Net Assets (ASC 958)",
    "Donor Restrictions and Releases",
    "Liquidity and Availability of Resources",
    "Endowment Funds and UPMIFA Disclosures",
    "Functional Expenses Allocation",
    "Contributions and Revenue Recognition",
    "Employee Benefit Plans",
    "Commitments and Contingencies",
    "Related Party Transactions",
    "Subsequent Events",
    "Risks and Uncertainties (ASC 275)",
    "Concentrations of Credit Risk",
    "Recent Accounting Pronouncements",
]
