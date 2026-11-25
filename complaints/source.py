"""Where the data comes from, and the exact snapshot this project is built on.

Source: the Consumer Complaint Database of the US Consumer Financial
Protection Bureau (CFPB): complaints about consumer financial products and
services that the CFPB sent to companies for a response.
https://www.consumerfinance.gov/data-research/consumer-complaints/

Licence: a work of the US Government, so in the public domain within the
United States. No key or sign-up is needed.

Two changes in 2026 shape this project (CFPB release notes,
https://cfpb.github.io/api/ccdb/release-notes.html):
* Release 23 (July 2026): filtered CSV exports from the API are capped at
  100,000 complaints, so the full bulk file is used instead of the API.
* Release 24 (September 2026): consumers' complaint narratives were removed
  from the database. The bulk file now has 15 structured columns and no
  free text.

The bulk file (~371 MB zipped) is replaced every day, so it is not
committed. scripts/download_data.py fetches it into data/raw/ (gitignored)
and builds two small files that are committed, with their SHA-256 pinned
below, so every later step runs on exactly the same data:

* SNAPSHOT_PATH: one row per complaint received in US federal fiscal year
  2026 (1 Oct 2025 to 30 Sep 2026) about any product except credit
  reporting.
* MONTHLY_PATH: complaints per month and product for the full history,
  including credit reporting.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BULK_URL = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
DATA_PAGE = "https://www.consumerfinance.gov/data-research/consumer-complaints/"
FIELDS_PAGE = "https://cfpb.github.io/api/ccdb/fields.html"
RELEASE_NOTES = "https://cfpb.github.io/api/ccdb/release-notes.html"

RAW_DIR = ROOT / "data" / "raw"
RAW_ZIP = RAW_DIR / "complaints.csv.zip"
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "complaints_fy2026.parquet"
MONTHLY_PATH = DATA_DIR / "monthly_by_product.csv"
MANIFEST_PATH = DATA_DIR / "SNAPSHOT.json"

# The analysis window: US federal fiscal year 2026 (dates as received).
WINDOW_START = "2025-10-01"
WINDOW_END = "2026-09-30"  # inclusive

# Credit reporting is ~90% of all complaints and is handled by a few
# consumer reporting agencies; it stays in the monthly history, not in the
# row-level snapshot.
CREDIT_REPORTING_PRODUCTS = (
    "Credit reporting or other personal consumer reports",
    "Credit reporting, credit repair services, or other personal consumer reports",
    "Credit reporting",
)

# The 15 columns of the bulk file since Release 24, in file order.
BULK_COLUMNS = (
    "Date received",
    "Product",
    "Sub-product",
    "Issue",
    "Sub-issue",
    "Company public response",
    "Company",
    "State",
    "ZIP code",
    "Tags",
    "Submitted via",
    "Date sent to company",
    "Company response to consumer",
    "Timely response?",
    "Complaint ID",
)

# Built on 2026-11-25 from the bulk file dated Tue, 24 Nov 2026 10:17:17 GMT
# (zip SHA-256 8b6db08e0f2d3c7af2a5e0c06c1e26b86c4411cffdceb4e78a8b327acb59dca2);
# see data/SNAPSHOT.json. A rebuild from that file gives these bytes again.
SNAPSHOT_SHA256 = "4b076522c7a9353f9dbb07c56203613d99b912861f9ac6f76113b6871c55b1eb"
MONTHLY_SHA256 = "13cd1cc56f127269d3960e31debb2dce4a2252c78d921e7b5bd106d3ab3d3828"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()
