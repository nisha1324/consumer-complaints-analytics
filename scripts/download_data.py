"""Check the committed snapshot, or rebuild it from the CFPB bulk file.

The two committed data files (data/complaints_fy2026.parquet and
data/monthly_by_product.csv) are all the analysis needs. Their SHA-256 is
pinned in complaints/source.py.

    python scripts/download_data.py              # check the committed files against the pinned hashes
    python scripts/download_data.py --rebuild    # download the bulk file (~371 MB zipped, ~5.9 GB unzipped),
                                                 # rebuild both files and write data/SNAPSHOT.json

The CFPB replaces the bulk file every day, and companies' responses to
recent complaints are still being filled in, so a rebuild on a later day
gives slightly different files and a hash mismatch. That is expected: the
rebuild reports both hashes; the analysis stays on the pinned snapshot
unless source.py is updated on purpose.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from complaints import build, source  # noqa: E402

# The CDN refuses unknown User-Agent strings with 403, so urllib's own default
# ("Python-urllib/3.x") is sent as is.


def download(url: str, dest: Path, timeout: int = 120) -> dict:
    """Stream the bulk zip to dest (via a .part file) and return its HTTP metadata."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(part, "wb") as out:
        meta = {"last_modified": resp.headers.get("Last-Modified"),
                "content_length": int(resp.headers.get("Content-Length") or 0)}
        shutil.copyfileobj(resp, out, length=1 << 20)
    size = part.stat().st_size
    if meta["content_length"] and size != meta["content_length"]:
        raise OSError(f"download incomplete: {size:,} of {meta['content_length']:,} bytes")
    part.replace(dest)
    return meta


def extract_csv(zip_path: Path, out_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if names != ["complaints.csv"]:
            raise ValueError(f"unexpected zip contents: {names}")
        zf.extract("complaints.csv", out_dir)
    return out_dir / "complaints.csv"


def check() -> int:
    ok = True
    for path, pinned in ((source.SNAPSHOT_PATH, source.SNAPSHOT_SHA256),
                         (source.MONTHLY_PATH, source.MONTHLY_SHA256)):
        if not path.exists():
            print(f"MISSING   {path.name} (run with --rebuild)", file=sys.stderr)
            ok = False
            continue
        digest = source.sha256_file(path)
        if digest != pinned:
            print(f"MISMATCH  {path.name}: pinned {str(pinned)[:12]}…, file {digest[:12]}…", file=sys.stderr)
            ok = False
        else:
            print(f"ok  {path.name}  {path.stat().st_size:,} bytes")
    return 0 if ok else 1


def rebuild(keep_csv: bool) -> int:
    print(f"downloading {source.BULK_URL} …")
    meta = download(source.BULK_URL, source.RAW_ZIP)
    zip_sha = source.sha256_file(source.RAW_ZIP)
    print(f"  {source.RAW_ZIP.stat().st_size:,} bytes, Last-Modified {meta['last_modified']}, sha256 {zip_sha[:12]}…")
    csv_path = extract_csv(source.RAW_ZIP, source.RAW_DIR)
    print(f"  extracted {csv_path.stat().st_size:,} bytes; building the snapshot (a few minutes) …")
    counts = build.build(csv_path)
    if not keep_csv:
        csv_path.unlink()
    manifest = {
        "source": source.BULK_URL,
        "licence": "US Government work, public domain within the United States",
        "bulk_last_modified": meta["last_modified"],
        "bulk_zip_bytes": source.RAW_ZIP.stat().st_size,
        "bulk_zip_sha256": zip_sha,
        "downloaded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"start": source.WINDOW_START, "end": source.WINDOW_END},
        "excluded_products": list(source.CREDIT_REPORTING_PRODUCTS),
        **counts,
        "snapshot_sha256": source.sha256_file(source.SNAPSHOT_PATH),
        "monthly_sha256": source.sha256_file(source.MONTHLY_PATH),
    }
    source.MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    for key, pinned in (("snapshot_sha256", source.SNAPSHOT_SHA256), ("monthly_sha256", source.MONTHLY_SHA256)):
        same = "matches the pinned hash" if manifest[key] == pinned else f"differs from the pinned {str(pinned)[:12]}…"
        print(f"  {key} {manifest[key][:12]}… {same}")
    print(f"wrote {source.MANIFEST_PATH.relative_to(source.ROOT)}: {json.dumps(counts)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rebuild", action="store_true", help="download the bulk file and rebuild both data files")
    ap.add_argument("--keep-csv", action="store_true", help="keep the 5.9 GB unzipped CSV in data/raw/")
    args = ap.parse_args()
    return rebuild(args.keep_csv) if args.rebuild else check()


if __name__ == "__main__":
    sys.exit(main())
