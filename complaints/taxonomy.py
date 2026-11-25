"""Old product names -> the CFPB's current products.

The CFPB renamed and regrouped its products twice: in April 2017 and in
August 2023. To compare years, every complaint is put under the product it
would be filed under today. Most old names map one to one. Four products
were split later, so their complaints are mapped by sub-product:

* "Credit card or prepaid card" (2017-2023) -> Credit card or Prepaid card;
* "Consumer Loan" (to 2017) -> Vehicle loan or lease, or the payday /
  personal loan product;
* "Credit reporting, credit repair services, or other personal consumer
  reports" (2017-2023) -> credit reporting, except credit repair services,
  which moved to "Debt or credit management" in 2023;
* "Other financial service" (2014-2017) -> money services, except credit
  repair and debt settlement (-> Debt or credit management).

A few sub-products also moved on their own (debt settlement filed under
money services, mobile wallets filed under prepaid cards, cashing a check
without an account filed under bank accounts); they follow the current
product too.

Current product names are as in the FY2026 snapshot (plus credit
reporting). Anything not listed keeps its name, and a test checks that every
(product, sub-product) pair in the history lands on a current product.
"""
from __future__ import annotations

import pandas as pd

CREDIT_REPORTING = "Credit reporting or other personal consumer reports"
CHECKING = "Checking or savings account"
CREDIT_CARD = "Credit card"
DEBT_COLLECTION = "Debt collection"
DEBT_MGMT = "Debt or credit management"
MONEY = "Money transfer, virtual currency, or money service"
MORTGAGE = "Mortgage"
PAYDAY = "Payday loan, title loan, personal loan, or advance loan"
PREPAID = "Prepaid card"
STUDENT = "Student loan"
VEHICLE = "Vehicle loan or lease"

CURRENT_PRODUCTS = (CREDIT_REPORTING, DEBT_COLLECTION, CREDIT_CARD, CHECKING, MONEY, MORTGAGE, VEHICLE,
                    STUDENT, PAYDAY, PREPAID, DEBT_MGMT)

# Short labels for charts and tables.
SHORT = {
    CREDIT_REPORTING: "Credit reporting",
    DEBT_COLLECTION: "Debt collection",
    CREDIT_CARD: "Credit card",
    CHECKING: "Checking or savings",
    MONEY: "Money transfer and services",
    MORTGAGE: "Mortgage",
    VEHICLE: "Vehicle loan or lease",
    STUDENT: "Student loan",
    PAYDAY: "Payday and personal loans",
    PREPAID: "Prepaid card",
    DEBT_MGMT: "Debt or credit management",
}

# Product as filed -> current product (the default for every sub-product).
BY_PRODUCT = {
    "Bank account or service": CHECKING,
    "Consumer Loan": PAYDAY,
    "Credit card or prepaid card": CREDIT_CARD,
    "Credit reporting": CREDIT_REPORTING,
    "Credit reporting, credit repair services, or other personal consumer reports": CREDIT_REPORTING,
    "Money transfers": MONEY,
    "Virtual currency": MONEY,
    "Other financial service": MONEY,
    "Payday loan": PAYDAY,
    "Payday loan, title loan, or personal loan": PAYDAY,
}

# (product as filed, sub-product) -> current product, where it differs from the default above.
BY_SUB_PRODUCT = {
    ("Bank account or service", "Cashing a check without an account"): MONEY,
    ("Consumer Loan", "Vehicle loan"): VEHICLE,
    ("Consumer Loan", "Vehicle lease"): VEHICLE,
    ("Credit card or prepaid card", "General-purpose prepaid card"): PREPAID,
    ("Credit card or prepaid card", "Gift card"): PREPAID,
    ("Credit card or prepaid card", "Government benefit card"): PREPAID,
    ("Credit card or prepaid card", "Payroll card"): PREPAID,
    ("Credit card or prepaid card", "Student prepaid card"): PREPAID,
    ("Credit reporting, credit repair services, or other personal consumer reports",
     "Credit repair services"): DEBT_MGMT,
    (MONEY, "Debt settlement"): DEBT_MGMT,
    ("Other financial service", "Credit repair"): DEBT_MGMT,
    ("Other financial service", "Debt settlement"): DEBT_MGMT,
    (PREPAID, "Mobile wallet"): MONEY,
}


def current_product(product: str, sub_product: str | None) -> str:
    return BY_SUB_PRODUCT.get((product, sub_product), BY_PRODUCT.get(product, product))


def map_table(pairs: pd.DataFrame) -> pd.DataFrame:
    """(product, sub_product) pairs -> the same pairs with current_product and how it was decided."""
    out = pairs[["product", "sub_product"]].drop_duplicates().reset_index(drop=True)
    subs = [None if pd.isna(s) else s for s in out["sub_product"]]
    out["current_product"] = [current_product(p, s) for p, s in zip(out["product"], subs)]
    out["rule"] = [
        "sub-product" if (p, s) in BY_SUB_PRODUCT else ("renamed" if p in BY_PRODUCT else "same name")
        for p, s in zip(out["product"], subs)
    ]
    return out
