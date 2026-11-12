#!/usr/bin/env python3
"""Read-only, standard-library inspection of the original IndPenSim ZIP.

Retains raw CSV positions: it does not repair headers, convert source units,
assign fault types, or calculate product acceptance outcomes.
"""
import collections
import csv
import hashlib
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data/raw/indpensim/100_Batches_IndPenSim.zip"
OUTPUT = ROOT / "docs/evidence/indpensim/inspection.json"
EXPECTED_SHA256 = "bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00"


def main():
    import zipfile

    digest = hashlib.sha256()
    with ARCHIVE.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != EXPECTED_SHA256:
        raise ValueError("Archive does not match Mendeley's published SHA-256")
    result = {"archive_bytes": ARCHIVE.stat().st_size, "sha256": digest.hexdigest()}
    with zipfile.ZipFile(ARCHIVE) as archive:
        result["members"] = [
            {"name": i.filename, "bytes": i.file_size,
             "compressed_bytes": i.compress_size, "crc32": f"{i.CRC:08x}"}
            for i in archive.infolist()
        ]
        with archive.open("Mendeley_data/100_Batches_IndPenSim_Statistics.csv") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
            result["statistics"] = {"headers": reader.fieldnames, "rows": list(reader)}
        with archive.open("Mendeley_data/100_Batches_IndPenSim_V3.csv") as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            headers = next(reader)
            result["raw_headers"] = headers
            widths = collections.Counter()
            batches = {}
            missing = collections.Counter()
            nonnumeric = collections.Counter()
            ranges = {}
            runs = collections.defaultdict(list)
            # Published correction identifies raw position 35 as the batch key.
            # Positions 37 onward are deliberately not assigned semantic names.
            for number, row in enumerate(reader, 1):
                widths[len(row)] += 1
                batch = int(float(row[35]))
                time = float(row[0])
                b = batches.setdefault(batch, {
                    "rows": 0, "start_h": time, "end_h": time,
                    "dt_h_counts": collections.Counter(),
                    "raw_metadata_values": {str(i): set() for i in range(31, 37)},
                    "offline_present_times_h": {str(i): [] for i in (21, 23, 26, 27, 30)},
                    "first_raw_values_0_42": row[:43],
                    "last_raw_values_0_42": [],
                    "spectral_tail_nonzero_rows": 0,
                })
                if b["rows"]:
                    b["dt_h_counts"][str(round(time - b["end_h"], 8))] += 1
                b["rows"] += 1
                b["end_h"] = time
                b["last_raw_values_0_42"] = row[:43]
                # Count whether any tail value is nonzero; do not reinterpret its axis.
                if any(v not in ("0", "-0", "0.0") for v in row[37:]):
                    b["spectral_tail_nonzero_rows"] += 1
                for i, value in enumerate(row[:37]):
                    try:
                        numeric = float(value)
                    except ValueError:
                        nonnumeric[str(i)] += 1
                        continue
                    if not math.isfinite(numeric):
                        missing[str(i)] += 1
                        continue
                    low, high = ranges.get(str(i), (numeric, numeric))
                    ranges[str(i)] = (min(low, numeric), max(high, numeric))
                    if i in (21, 23, 26, 27, 30):
                        b["offline_present_times_h"][str(i)].append(time)
                for i in range(31, 37):
                    b["raw_metadata_values"][str(i)].add(row[i])
                code = row[31]
                rr = runs[batch]
                if rr and rr[-1]["raw_fault_reference"] == code:
                    rr[-1]["end_h"] = time
                    rr[-1]["rows"] += 1
                else:
                    rr.append({"raw_fault_reference": code, "start_h": time,
                               "end_h": time, "rows": 1})
                if number % 25000 == 0:
                    print(f"Inspected {number:,} rows", flush=True)
            result["process_rows"] = sum(widths.values())
            result["row_width_counts"] = dict(widths)
            result["process_nonfinite_counts_by_raw_position"] = dict(missing)
            result["process_nonnumeric_counts_by_raw_position"] = dict(nonnumeric)
            result["process_ranges_by_raw_position"] = ranges
            for batch, b in batches.items():
                b["dt_h_counts"] = dict(b["dt_h_counts"])
                b["raw_metadata_values"] = {
                    k: sorted(v, key=float) for k, v in b["raw_metadata_values"].items()
                }
                b["raw_fault_reference_runs"] = runs[batch]
            result["batches_by_documented_raw_position_35"] = batches
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {OUTPUT}; {result['process_rows']:,} data rows", flush=True)


if __name__ == "__main__":
    main()
