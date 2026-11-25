"""Shared fixtures: a toy bulk CSV in the CFPB's exact format."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from complaints import source


def bulk_row(cid, received="2026-01-15", product="Credit card", company="ACME BANK", sent=None,
             response="Closed with explanation", timely="Yes", state="TX", zip_code="75001",
             sub_product="General-purpose credit card or charge card", issue="Fees or interest",
             sub_issue="Problem with fees", tags="", via="Web", public=""):
    return {
        "Date received": received, "Product": product, "Sub-product": sub_product, "Issue": issue,
        "Sub-issue": sub_issue, "Company public response": public, "Company": company, "State": state,
        "ZIP code": zip_code, "Tags": tags, "Submitted via": via, "Date sent to company": sent or received,
        "Company response to consumer": response, "Timely response?": timely, "Complaint ID": str(cid),
    }


def write_bulk(path: Path, rows: list[dict], columns=source.BULK_COLUMNS) -> Path:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(columns), quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    return path


@pytest.fixture
def toy_rows():
    return [
        bulk_row(5, received="2025-10-01"),                                   # first day of the window
        bulk_row(3, received="2026-09-30", product="Debt collection",          # last day of the window
                 company='Collector, "Inc."', issue="Attempts to collect debt not owed", sub_issue=""),
        bulk_row(4, received="2025-09-30"),                                   # day before: out
        bulk_row(6, received="2026-10-01"),                                   # day after: out
        bulk_row(7, received="2026-02-02", product="Credit reporting or other personal consumer reports"),
        bulk_row(8, received="2026-02-02",
                 product="Credit reporting, credit repair services, or other personal consumer reports"),
        bulk_row(1, received="2026-03-03", product="Mortgage", response="Untimely response", timely="No",
                 sent="2026-03-20", state="", zip_code="XXXXX", tags="Older American, Servicemember"),
        bulk_row(2, received="2016-05-05", product="Bank account or service"),  # history only
    ]
