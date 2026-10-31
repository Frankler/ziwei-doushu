#!/usr/bin/env python3
"""Build 16 deterministic, browser-readable v4 interpretation shards per year.

The original v4 dataset is downloaded by GitHub Actions, SHA-256 verified,
and streamed from zstd into independent gzip files. Each shard is under
GitHub's 100 MiB per-file limit. No personal birth data is sent to a backend.
"""
import calendar
import gzip
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys

SHARD_COUNT = 16
MAX_FILE_BYTES = 90 * 1024 * 1024  # Leave margin below GitHub's 100 MiB rejection threshold.


def shard_for_key(key: str) -> int:
    # Keep this in sync with components/PrivateInterpretation.tsx
    return hashlib.sha256(key.encode("utf-8")).digest()[0] & (SHARD_COUNT - 1)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/prepare-v4-year.py YEAR year-YYYY.jsonl.zst")
    year = int(sys.argv[1])
    if not 1950 <= year <= 2026:
        raise SystemExit("v4 dataset only covers 1950–2026")
    source = Path(sys.argv[2])
    if not source.is_file():
        raise FileNotFoundError(source)
    output_dir = Path("public/interpretations") / str(year)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = [output_dir / f"b{n:02d}.jsonl.gz" for n in range(SHARD_COUNT)]
    counts = [0] * SHARD_COUNT
    total = 0
    try:
        with ExitStack() as stack:
            writers = []
            for path in paths:
                fileobj = stack.enter_context(path.open("wb"))
                writers.append(stack.enter_context(gzip.GzipFile(
                    filename="", fileobj=fileobj, mode="wb", compresslevel=6, mtime=0
                )))

            process = subprocess.Popen(
                ["zstd", "-d", "--long=27", "-c", str(source)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert process.stdout is not None
            for raw_line in process.stdout:
                if not raw_line.endswith(b"\n"):
                    raise ValueError("Unexpected unterminated JSONL record")
                record = json.loads(raw_line)
                key = record.get("k")
                if not isinstance(key, str) or record.get("y") != year or not isinstance(record.get("c"), dict):
                    raise ValueError("Unexpected v4 record schema")
                # Check key and record fields agree; avoid silently publishing corrupt readings.
                expected_key = (f"{record['y']:04d}-{record['m']:02d}-{record['d']:02d}-"
                                f"{record['h']}-{record['g']}")
                if key != expected_key:
                    raise ValueError(f"Dataset record key mismatch: {key}")
                index = shard_for_key(key)
                writers[index].write(raw_line)
                counts[index] += 1
                total += 1
            process.stdout.close()
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            if process.wait() != 0:
                raise RuntimeError(f"zstd failed: {stderr[:500]}")

        expected = (366 if calendar.isleap(year) else 365) * 24
        if total != expected:
            raise ValueError(f"Expected {expected} charts; received {total}")
        for n, path in enumerate(paths):
            size = path.stat().st_size
            if counts[n] == 0 or size >= MAX_FILE_BYTES:
                raise ValueError(f"Bad shard {n}: {counts[n]} charts, {size} bytes")
            print(f"{path}: {counts[n]} charts; {size:,} bytes")
        print(f"Success: {total} total charts across {SHARD_COUNT} shards")
    except BaseException:
        for path in paths:
            path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
