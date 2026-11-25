"""The snapshot builder on a toy bulk file, checked by hand."""
from __future__ import annotations

import zipfile
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from complaints import build, source
from scripts import download_data
from tests.conftest import bulk_row, write_bulk


@pytest.fixture
def built(tmp_path, toy_rows):
    csv_path = write_bulk(tmp_path / "complaints.csv", toy_rows)
    snap, monthly = tmp_path / "snap.parquet", tmp_path / "monthly.csv"
    counts = build.build(csv_path, snap, monthly)
    df = duckdb.sql(f"SELECT * FROM read_parquet('{snap}')").df()
    return counts, df, pd.read_csv(monthly), snap, monthly, csv_path


def test_window_and_product_filter(built):
    counts, df, *_ = built
    # in: 5 (first day), 3 (last day), 1 (mortgage). Out: 4, 6 (dates), 7, 8 (credit reporting), 2 (2016)
    assert df["complaint_id"].tolist() == [1, 3, 5]
    # 8 rows, each in its own month and product pair (the two February rows are different products)
    assert counts == {"bulk_rows": 8, "snapshot_rows": 3, "monthly_rows": 8, "monthly_total": 8}


def test_columns_names_and_types(built):
    _, df, *_ = built
    assert list(df.columns) == list(build.RENAME.values())
    assert str(df["date_received"].dtype).startswith("datetime64")
    assert df["timely_response"].tolist() == [False, True, True]
    row = df.set_index("complaint_id").loc[1]
    assert row["company_response"] == "Untimely response"
    assert pd.isna(row["state"])                       # empty in the CSV -> NULL
    assert row["zip_code"] == "XXXXX"
    assert row["tags"] == "Older American, Servicemember"
    assert (row["date_sent_to_company"] - row["date_received"]).days == 17


def test_quoted_values_survive(built):
    _, df, *_ = built
    row = df.set_index("complaint_id").loc[3]
    assert row["company"] == 'Collector, "Inc."'
    assert pd.isna(row["sub_issue"])


def test_monthly_history_keeps_everything(built):
    _, _, monthly, *_ = built
    assert monthly["complaints"].sum() == 8
    assert monthly["month"].tolist() == sorted(monthly["month"].tolist())
    feb = monthly[monthly["month"] == "2026-02"]
    assert sorted(feb["product"]) == sorted(source.CREDIT_REPORTING_PRODUCTS[:2])
    assert monthly.loc[monthly["month"] == "2016-05", "product"].item() == "Bank account or service"


def test_rebuild_is_byte_identical(built, tmp_path):
    _, _, _, snap, monthly, csv_path = built
    snap2, monthly2 = tmp_path / "snap2.parquet", tmp_path / "monthly2.csv"
    build.build(csv_path, snap2, monthly2)
    assert snap.read_bytes() == snap2.read_bytes()
    assert monthly.read_bytes() == monthly2.read_bytes()


def test_unexpected_columns_fail(tmp_path):
    cols = list(source.BULK_COLUMNS) + ["Consumer complaint narrative"]
    path = write_bulk(tmp_path / "c.csv", [bulk_row(1)], columns=cols)
    with pytest.raises(ValueError, match="unexpected bulk-file columns"):
        build.build(path, tmp_path / "s.parquet", tmp_path / "m.csv")


def test_bad_timely_value_becomes_null(tmp_path):
    path = write_bulk(tmp_path / "c.csv", [bulk_row(1, timely="Maybe")])
    build.build(path, tmp_path / "s.parquet", tmp_path / "m.csv")
    df = duckdb.sql(f"SELECT timely_response FROM read_parquet('{tmp_path / 's.parquet'}')").df()
    assert df["timely_response"].isna().all()


def test_malformed_date_fails(tmp_path):
    path = write_bulk(tmp_path / "c.csv", [bulk_row(1), bulk_row(2, received="15/01/2026")])
    with pytest.raises(duckdb.Error):
        build.build(path, tmp_path / "s.parquet", tmp_path / "m.csv")


def test_extract_rejects_unexpected_zip(tmp_path):
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("other.csv", "a\n")
    with pytest.raises(ValueError, match="unexpected zip contents"):
        download_data.extract_csv(z, tmp_path)


def test_extract_and_download_from_local_url(tmp_path, toy_rows):
    csv_path = write_bulk(tmp_path / "complaints.csv", toy_rows)
    z = tmp_path / "src.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(csv_path, "complaints.csv")
    dest = tmp_path / "raw" / "complaints.csv.zip"
    meta = download_data.download(z.as_uri(), dest)
    assert dest.read_bytes() == z.read_bytes()
    assert meta["content_length"] == z.stat().st_size
    assert not dest.with_suffix(".zip.part").exists()
    out = download_data.extract_csv(dest, tmp_path / "raw")
    assert out.read_bytes() == csv_path.read_bytes()


def test_selected_sql_uses_the_window_in_source():
    q = build.snapshot_select(Path("x.csv"))
    assert f"DATE '{source.WINDOW_START}' AND DATE '{source.WINDOW_END}'" in q
    for p in source.CREDIT_REPORTING_PRODUCTS:
        assert f"'{p}'" in q


def test_company_history(tmp_path, toy_rows):
    rows = toy_rows + [bulk_row(9, received="2026-01-20", company="OTHER BANK"),
                       bulk_row(10, received="2026-01-03"), bulk_row(12),   # default date: 15 Jan 2026
                       bulk_row(11, received="2016-05-09", product="Bank account or service", sub_product="")]
    csv_path = write_bulk(tmp_path / "complaints.csv", rows)
    comp = tmp_path / "company.parquet"
    counts = build.build(csv_path, tmp_path / "s.parquet", tmp_path / "m.csv", comp)
    df = duckdb.sql(f"SELECT * FROM read_parquet('{comp}')").df()
    assert list(df.columns) == ["month", "product", "sub_product", "company", "complaints"]
    assert counts["company_monthly_total"] == df["complaints"].sum() == len(rows) == counts["bulk_rows"]
    assert counts["company_monthly_rows"] == len(df)
    jan = df[(df["month"] == "2026-01") & (df["product"] == "Credit card")].set_index("company")["complaints"]
    assert jan.to_dict() == {"ACME BANK": 2, "OTHER BANK": 1}      # 15 Jan and 3 Jan together; sorted by company
    may16 = df[df["month"] == "2016-05"]
    assert may16["sub_product"].isna().tolist() == [True, False]    # empty sub-product -> NULL, sorted first
    assert may16["complaints"].tolist() == [1, 1]
    # credit reporting stays in the company history
    assert df["product"].isin(source.CREDIT_REPORTING_PRODUCTS).sum() == 2
    comp2 = tmp_path / "company2.parquet"
    build.build(csv_path, tmp_path / "s2.parquet", tmp_path / "m2.csv", comp2, threads=2)
    assert comp.read_bytes() == comp2.read_bytes()


def test_company_history_is_optional(built):
    counts, *_ = built
    assert "company_monthly_rows" not in counts
