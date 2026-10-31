#!/usr/bin/env python3
"""Stream one upstream v4 .zst year into a browser-friendly deterministic .gz.

Does not buffer a year's ~700MB of JSONL in RAM. No birth data is used here.
"""
import calendar
import gzip
import json
from pathlib import Path
import subprocess
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/prepare-v4-year.py YEAR year-YYYY.jsonl.zst")
    year = int(sys.argv[1])
    if not 1950 <= year <= 2026:
        raise SystemExit("v4 dataset only covers 1950–2026")
    source = Path(sys.argv[2])
    dest = Path("public/interpretations") / f"{year}.jsonl.gz"
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    first_key = None
    last_key = None

    try:
        with dest.open("wb") as file:
            with gzip.GzipFile(fileobj=file, filename="", mode="wb", compresslevel=6, mtime=0) as zipped:
                proc = subprocess.Popen(
                    ["zstd", "-d", "--long=27", "-c", str(source)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                assert proc.stdout is not None
                for raw_line in proc.stdout:
                    if not raw_line.endswith(b"\n"):
                        raise ValueError("Unexpected unterminated JSONL record")
                    # Full data is preserved verbatim, including all 13 Markdown topics.
                    if count == 0:
                        record = json.loads(raw_line)
                        first_key = record.get("k")
                        if record.get("y") != year or not isinstance(record.get("c"), dict):
                            raise ValueError("Unexpected v4 record schema")
                    count += 1
                    if b'"k"' in raw_line:
                        # Cheap end-of-year check without parsing all ~700MB.
                        last_key = raw_line[:100]
                    zipped.write(raw_line)
                proc.stdout.close()
                stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                if proc.wait() != 0:
                    raise RuntimeError(f"zstd failed: {stderr[:300]}")
        expected = (366 if calendar.isleap(year) else 365) * 12 * 2
        if count != expected or not str(first_key).startswith(f"{year}-"):
            raise ValueError(f"Invalid number of charts: {count} (expected {expected})")
        print(f"Wrote {dest}: {count} charts; {dest.stat().st_size:,} bytes compressed")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
