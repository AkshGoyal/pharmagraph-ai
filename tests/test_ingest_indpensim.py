"""Independent checks for the pinned ingestion contract, using synthetic fixtures.

Fixtures deliberately keep the source's malformed 2,239-field header and
2,237-value records. They use a distinct dataset identity and must never be
presented as IndPenSim observations. Full-data runs are the lead's separate
acceptance evidence.
"""
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_CONTRACT = ROOT / "config/indpensim_contract.json"
SCRIPT = ROOT / "scripts/ingest_indpensim.py"
DATASET = "test:synthetic-ingestion-fixture:v1"
OUTPUT_NAMES = ("batches.parquet", "samples.parquet", "variables.parquet", "manifest.json")
SPARSE_POSITIONS = (21, 23, 26, 27, 30)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_implementation():
    spec = importlib.util.spec_from_file_location("indpensim_ingestion_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rewrite_identity(value, original):
    if isinstance(value, str):
        return value.replace(original, DATASET)
    if isinstance(value, list):
        return [rewrite_identity(item, original) for item in value]
    if isinstance(value, dict):
        return {key: rewrite_identity(item, original) for key, item in value.items()}
    return value


def csv_bytes(header, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


class Fixture:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.archive = self.directory / "fixture.zip"
        self.contract_path = self.directory / "fixture_contract.json"
        self.output = self.directory / "output"
        production = json.loads(PRODUCTION_CONTRACT.read_text())
        self.contract = rewrite_identity(production, production["dataset"]["id"])
        self.contract["dataset"].update({
            "name": "Synthetic fixture, not published IndPenSim data",
            "repository_id": "test-fixture",
            "doi": "test:no-doi",
            "url": "https://example.invalid/ingestion-fixture",
        })
        self.contract["source"]["archive_filename"] = self.archive.name
        self.contract["source"]["expected_batch_refs"] = [1, 61, 91]
        self.statistics = [
            ["91", "1000001", "2000002", "3000003", "1"],
            ["1", "1000004", "2000005", "3000009", "0"],
            ["61", "1000006", "2000007", "3000013", "0"],
        ]
        self.samples = []
        # Deliberately not sorted by batch. Provenance must retain this order,
        # while table rows and stable IDs use the canonical batch/tick order.
        for batch in (91, 1, 61):
            for tick in (1, 2):
                row = ["0"] * 2237
                row[0] = "0.2" if tick == 1 else "0.4"
                for position in range(1, 31):
                    row[position] = str(batch * 100 + tick + position / 100)
                row[10] = "-7.5"
                row[25] = "0.21"  # Must remain as source value, not 21 percent.
                for position in SPARSE_POSITIONS:
                    row[position] = "NaN" if tick == 1 else "123.456"
                row[31] = str(int(batch == 91 and tick == 2))
                row[32] = "0"
                row[33] = "2" if batch == 61 else "1"
                row[34] = row[35] = str(batch)
                row[36] = str(int(batch == 91))
                row[37] = "198765.5"  # Misleading Batch ID header; not an ID.
                row[38] = "198999.5"  # Misleading Fault flag; not ground truth.
                self.samples.append(row)
        self.timeseries_header = copy.deepcopy(self.contract["source"]["members"][1]["expected_header"])
        self.statistics_header = copy.deepcopy(self.contract["source"]["members"][0]["expected_header"])
        self.write()

    def write(self):
        members = self.contract["source"]["members"]
        payloads = [csv_bytes(self.statistics_header, self.statistics),
                    csv_bytes(self.timeseries_header, self.samples)]
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member, payload in zip(members, payloads):
                info = zipfile.ZipInfo(member["path"], date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, payload)
        with zipfile.ZipFile(self.archive) as archive:
            for member, rows in zip(members, (self.statistics, self.samples)):
                info = archive.getinfo(member["path"])
                member.update(expected_bytes=info.file_size,
                              expected_crc32=f"{info.CRC:08x}",
                              expected_rows=len(rows))
        self.contract["source"].update(expected_sha256=sha256(self.archive),
                                       expected_bytes=self.archive.stat().st_size)
        self.save_contract()

    def save_contract(self):
        self.contract_path.write_text(json.dumps(self.contract, indent=2) + "\n")


class IngestionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ingestion = load_implementation()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pharmagraph-tests-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(self.temp.name)

    def ingest(self, *, force=False, output=None):
        f = self.fixture
        return self.ingestion.ingest(f.archive, output or f.output,
                                     force=force, contract_path=f.contract_path)

    def snapshot(self, output=None):
        output = output or self.fixture.output
        return {name: (sha256(output / name), (output / name).stat().st_mtime_ns,
                       (output / name).stat().st_ino)
                for name in OUTPUT_NAMES}

    def read_manifest(self):
        return json.loads((self.fixture.output / "manifest.json").read_text())

    def change_manifest(self, mutate):
        manifest = self.read_manifest()
        mutate(manifest)
        (self.fixture.output / "manifest.json").write_text(json.dumps(manifest) + "\n")

    def assert_fixture_value(self, value, token):
        if token == "NaN":
            self.assertIsNone(value)
        else:
            self.assertEqual(value, float(token))

    def test_schema_values_identity_and_source_row_traceability(self):
        result = self.ingest()
        self.assertEqual(result["status"], "built")
        f = self.fixture
        for table_name, rows in (("batches", 3), ("samples", 6), ("variables", 33)):
            table = pq.read_table(f.output / (table_name + ".parquet"))
            expected = pa.schema([pa.field(field["name"], pa.type_for_alias(field["type"]),
                                           nullable=field["nullable"])
                                  for field in f.contract["schemas"][table_name]])
            self.assertEqual(table.schema, expected)
            self.assertEqual(table.num_rows, rows)
        samples = pq.read_table(f.output / "samples.parquet").to_pylist()
        self.assertEqual([(r["batch_ref"], r["time_tick"]) for r in samples],
                         [(1, 1), (1, 2), (61, 1), (61, 2), (91, 1), (91, 2)])
        self.assertEqual(len({r["sample_id"] for r in samples}), 6)
        for record in samples:
            raw = f.samples[record["source_row_number"] - 1]
            self.assertEqual(record["dataset_id"], DATASET)
            self.assertEqual(record["source_file_id"], DATASET + ":timeseries")
            self.assertEqual(record["batch_ref"], int(raw[35]))
            self.assertEqual(record["batch_id"], DATASET + f":batch:{int(raw[35]):03d}")
            self.assertEqual(record["sample_id"], record["batch_id"] + f":tick:{record['time_tick']:06d}")
            self.assertEqual(record["time_h"], float(raw[0]))
            self.assertEqual(record["fault_reference_raw"], int(raw[31]))
            self.assertEqual(record["batch_fault_flag_raw"], int(raw[36]))
            for variable in f.contract["variables"]:
                if variable["output_table"] == "samples":
                    self.assert_fixture_value(record[variable["output_column"]],
                                              raw[variable["source_column_index"]])
            self.assertEqual(record["dumped_broth_flow"], -7.5)
            self.assertEqual(record["o2_offgas"], 0.21)
            self.assertNotIn("Fault flag", record)
            self.assertNotIn("fault_type", record)
            self.assertNotIn("2400", record)
        batches = pq.read_table(f.output / "batches.parquet").to_pylist()
        self.assertEqual([r["control_regime"] for r in batches],
                         ["recipe_driven", "apc_raman", "not_documented"])
        for record in batches:
            raw = f.statistics[record["source_row_number"] - 1]
            self.assertEqual(record["batch_ref"], int(raw[0]))
            self.assertEqual(record["fault_present"], raw[4] == "1")
            self.assertEqual(record["harvest_total_raw"], float(raw[3]))
            matching = [s for s in samples if s["batch_id"] == record["batch_id"]]
            self.assertEqual(record["sample_count"], len(matching))
            self.assertEqual(record["time_start_h"], 0.2)
            self.assertEqual(record["time_end_h"], 0.4)
            self.assertEqual(record["timeseries_first_source_row"], min(s["source_row_number"] for s in matching))
            self.assertEqual(record["timeseries_last_source_row"], max(s["source_row_number"] for s in matching))
        variables = pq.read_table(f.output / "variables.parquet").to_pylist()
        self.assertEqual(variables, [dict(dataset_id=DATASET, **v) for v in f.contract["variables"]])
        self.assertTrue(all(v["unit_status"] == "unresolved" for v in variables
                            if v["output_column"] in ("paa_offline", "nh3_offline", "o2_offgas",
                                                      "harvest_during_batch_raw", "harvest_end_of_batch_raw", "harvest_total_raw")))

    def test_manifest_hashes_metadata_and_warning_traceability(self):
        self.ingest()
        f = self.fixture
        manifest = self.read_manifest()
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["contract_version"], f.contract["contract_version"])
        self.assertEqual(manifest["dataset"], f.contract["dataset"])
        self.assertEqual(manifest["source"]["sha256"], sha256(f.archive))
        self.assertEqual(manifest["source"]["bytes"], f.archive.stat().st_size)
        self.assertEqual(manifest["source"]["archive_filename"], f.archive.name)
        self.assertEqual(manifest["cache_inputs"]["contract_sha256"], sha256(f.contract_path))
        self.assertEqual(manifest["cache_inputs"]["normalizer_sha256"], sha256(SCRIPT))
        self.assertEqual(manifest["cache_inputs"]["archive_sha256"], sha256(f.archive))
        self.assertEqual(manifest["cache_inputs"]["pyarrow_version"], pa.__version__)
        canonical = json.dumps(manifest["cache_inputs"], sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(manifest["cache_key"], hashlib.sha256(canonical).hexdigest())
        self.assertEqual(manifest["normalization"], f.contract["normalization"])
        self.assertEqual(manifest["writer"], f.contract["writer"])
        self.assertIsInstance(manifest["warnings"], list)
        self.assertTrue(manifest["warnings"])
        self.assertEqual(set(manifest["outputs"]), set(OUTPUT_NAMES) - {"manifest.json"})
        for name, metadata in manifest["outputs"].items():
            path = f.output / name
            table = pq.read_table(path)
            self.assertEqual(metadata["sha256"], sha256(path))
            self.assertEqual(metadata["bytes"], path.stat().st_size)
            self.assertEqual(metadata["rows"], table.num_rows)
            self.assertEqual(metadata["schema"], f.contract["schemas"][name.removesuffix(".parquet")])
        for source, expected in zip(manifest["source"]["members"], f.contract["source"]["members"]):
            self.assertEqual(source["source_file_id"], expected["source_file_id"])
            self.assertEqual(source["path"], expected["path"])
            self.assertEqual(source["bytes"], expected["expected_bytes"])
            self.assertEqual(source["crc32"], expected["expected_crc32"])
            self.assertEqual(source["rows"], expected["expected_rows"])
            self.assertEqual(source["header_fields"], len(expected["expected_header"]))
            self.assertEqual(source["row_fields"], expected["expected_row_width"])
        serialized = (f.output / "manifest.json").read_text()
        self.assertTrue(serialized.endswith("\n"))
        self.assertNotIn(str(Path(self.temp.name).resolve()), serialized)

    def test_cached_second_run_reuses_files_without_writes(self):
        self.ingest()
        before = self.snapshot()
        result = self.ingest()
        self.assertEqual(result["status"], "cached")
        self.assertEqual(before, self.snapshot())

    def test_force_rebuild_replaces_files_with_identical_hashes(self):
        first = self.ingest()
        before = self.snapshot()
        second = self.ingest(force=True)
        after = self.snapshot()
        self.assertEqual(second["status"], "built")
        self.assertEqual(first["cache_key"], second["cache_key"])
        self.assertEqual({k: v[0] for k, v in before.items()}, {k: v[0] for k, v in after.items()})
        self.assertTrue(all(before[k][2] != after[k][2] for k in OUTPUT_NAMES))

    def test_independent_output_directory_has_identical_bytes(self):
        self.ingest()
        second_dir = Path(self.temp.name) / "elsewhere"
        self.assertEqual(self.ingest(output=second_dir)["status"], "built")
        self.assertEqual({n: sha256(self.fixture.output / n) for n in OUTPUT_NAMES},
                         {n: sha256(second_dir / n) for n in OUTPUT_NAMES})

    def test_stable_ids_are_independent_of_source_record_order(self):
        self.ingest()
        before = pq.read_table(self.fixture.output / "samples.parquet").to_pylist()
        f = self.fixture
        f.samples = f.samples[2:4] + f.samples[4:] + f.samples[:2]
        f.statistics = list(reversed(f.statistics))
        f.write()
        self.ingest()
        after = pq.read_table(f.output / "samples.parquet").to_pylist()
        self.assertEqual([(r["batch_ref"], r["time_tick"], r["sample_id"]) for r in before],
                         [(r["batch_ref"], r["time_tick"], r["sample_id"]) for r in after])
        self.assertNotEqual([r["source_row_number"] for r in before],
                            [r["source_row_number"] for r in after])

    def test_missing_outputs_are_rebuilt(self):
        self.ingest()
        expected = {n: sha256(self.fixture.output / n) for n in OUTPUT_NAMES}
        for missing in OUTPUT_NAMES:
            with self.subTest(missing=missing):
                (self.fixture.output / missing).unlink()
                self.assertEqual(self.ingest()["status"], "built")
                self.assertEqual(expected, {n: sha256(self.fixture.output / n) for n in OUTPUT_NAMES})

    def test_corrupt_outputs_and_manifest_are_rebuilt(self):
        self.ingest()
        expected = {n: sha256(self.fixture.output / n) for n in OUTPUT_NAMES}
        for corrupt in OUTPUT_NAMES:
            with self.subTest(corrupt=corrupt):
                path = self.fixture.output / corrupt
                path.write_bytes(b"not a parquet or JSON file\n")
                self.assertEqual(self.ingest()["status"], "built")
                self.assertEqual(expected, {n: sha256(self.fixture.output / n) for n in OUTPUT_NAMES})

    def test_same_size_output_corruption_is_not_reused(self):
        self.ingest()
        path = self.fixture.output / "samples.parquet"
        original = path.read_bytes()
        corrupted = bytearray(original)
        corrupted[len(corrupted) // 2] ^= 1
        path.write_bytes(corrupted)
        self.assertEqual(path.stat().st_size, len(original))
        self.assertEqual(self.ingest()["status"], "built")
        self.assertEqual(path.read_bytes(), original)

    def test_manifest_metadata_tampering_is_not_reused(self):
        self.ingest()
        mutations = {
            "dataset": lambda m: m["dataset"].update(license="made-up"),
            "source_crc": lambda m: m["source"]["members"][0].update(crc32="00000000"),
            "normalization": lambda m: m["normalization"].update(time_step_h="99"),
            "writer": lambda m: m["writer"].update(compression="none"),
            "rows": lambda m: m["outputs"]["samples.parquet"].update(rows=7),
            "schema": lambda m: m["outputs"]["samples.parquet"]["schema"][0].update(nullable=True),
            "missing_warning": lambda m: m.pop("warnings"),
            "missing_output": lambda m: m["outputs"].pop("variables.parquet"),
            "extra_output": lambda m: m["outputs"].update({"invented.parquet": {}}),
            "cache_input": lambda m: m["cache_inputs"].update(normalizer_sha256="0" * 64),
        }
        original = (self.fixture.output / "manifest.json").read_bytes()
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.change_manifest(mutate)
                self.assertEqual(self.ingest()["status"], "built")
                self.assertEqual((self.fixture.output / "manifest.json").read_bytes(), original)

    def test_unreadable_parquet_is_rebuilt_even_if_manifest_hash_is_updated(self):
        self.ingest()
        path = self.fixture.output / "samples.parquet"
        original = path.read_bytes()
        path.write_bytes(b"x" * len(original))
        self.change_manifest(lambda m: m["outputs"]["samples.parquet"].update(sha256=sha256(path)))
        self.assertEqual(self.ingest()["status"], "built")
        self.assertEqual(path.read_bytes(), original)

    def test_wrong_parquet_schema_is_rebuilt_even_with_updated_hash(self):
        self.ingest()
        path = self.fixture.output / "samples.parquet"
        original = path.read_bytes()
        table = pq.read_table(path)
        wrong = table.drop(["source_row_number"])
        pq.write_table(wrong, path)
        self.change_manifest(lambda m: m["outputs"]["samples.parquet"].update(
            sha256=sha256(path), bytes=path.stat().st_size))
        self.assertEqual(self.ingest()["status"], "built")
        self.assertEqual(path.read_bytes(), original)

    def test_changed_contract_invalidates_cache(self):
        first = self.ingest()
        self.fixture.contract["dataset"]["name"] += " revised description"
        self.fixture.save_contract()
        second = self.ingest()
        self.assertEqual(second["status"], "built")
        self.assertNotEqual(first["cache_key"], second["cache_key"])
        self.assertEqual(self.read_manifest()["dataset"], self.fixture.contract["dataset"])

    def test_source_hash_is_checked_on_cached_and_forced_runs(self):
        self.ingest()
        before = self.snapshot()
        original = self.fixture.archive.read_bytes()
        corrupt = bytearray(original)
        corrupt[len(corrupt) // 2] ^= 1
        self.fixture.archive.write_bytes(corrupt)
        for force in (False, True):
            with self.subTest(force=force):
                with self.assertRaises(ValueError):
                    self.ingest(force=force)
                self.assertEqual(before, self.snapshot())

    def test_source_size_and_member_metadata_are_enforced(self):
        cases = ("archive_size", "member_size", "member_crc", "member_rows", "header")
        for case in cases:
            with self.subTest(case=case):
                f = Fixture(Path(self.temp.name) / case)
                if case == "archive_size":
                    f.contract["source"]["expected_bytes"] += 1
                elif case == "member_size":
                    f.contract["source"]["members"][1]["expected_bytes"] += 1
                elif case == "member_crc":
                    f.contract["source"]["members"][1]["expected_crc32"] = "00000000"
                elif case == "member_rows":
                    f.contract["source"]["members"][1]["expected_rows"] += 1
                else:
                    f.timeseries_header[0] = "unexpected time header"
                    f.write()  # Update byte-integrity expectations, not expected header.
                f.save_contract()
                with self.assertRaises(ValueError):
                    self.ingestion.ingest(f.archive, f.output, contract_path=f.contract_path)
                self.assertFalse((f.output / "manifest.json").exists())

    def test_bad_row_width_is_rejected_without_new_outputs(self):
        self.fixture.samples[0].pop()
        self.fixture.write()
        with self.assertRaises(ValueError):
            self.ingest()
        self.assertFalse((self.fixture.output / "manifest.json").exists())

    def test_bad_values_ticks_keys_and_labels_are_rejected(self):
        mutations = {
            "nan_online": lambda f: f.samples[0].__setitem__(1, "NaN"),
            "inf_offline": lambda f: f.samples[0].__setitem__(21, "inf"),
            "blank_offline": lambda f: f.samples[0].__setitem__(21, ""),
            "nonnumeric": lambda f: f.samples[0].__setitem__(1, "broken"),
            "nonintegral_tick": lambda f: f.samples[0].__setitem__(0, "0.21"),
            "zero_tick": lambda f: f.samples[0].__setitem__(0, "0"),
            "negative_tick": lambda f: f.samples[0].__setitem__(0, "-0.2"),
            "duplicate_tick": lambda f: f.samples[1].__setitem__(0, "0.2"),
            "tick_gap": lambda f: f.samples[1].__setitem__(0, "0.6"),
            "noninteger_key": lambda f: f.samples[0].__setitem__(35, "91.5"),
            "mismatched_key_copy": lambda f: f.samples[0].__setitem__(34, "92"),
            "mismatched_batch_fault": lambda f: f.samples[0].__setitem__(36, "0"),
            "nonbinary_fault": lambda f: f.samples[0].__setitem__(31, "2"),
            "nonbinary_control": lambda f: f.samples[0].__setitem__(32, "2"),
            "statistics_duplicate": lambda f: f.statistics[0].__setitem__(0, "1"),
            "statistics_nonbinary_fault": lambda f: f.statistics[0].__setitem__(4, "2"),
            "statistics_missing_batch": lambda f: f.statistics.pop(),
            "extra_source_batch": lambda f: (f.samples[0].__setitem__(34, "92"), f.samples[0].__setitem__(35, "92")),
        }
        for case, mutate in mutations.items():
            with self.subTest(case=case):
                f = Fixture(Path(self.temp.name) / case)
                mutate(f)
                f.write()
                with self.assertRaises(ValueError):
                    self.ingestion.ingest(f.archive, f.output, contract_path=f.contract_path)
                self.assertFalse((f.output / "manifest.json").exists())

    def test_failed_staging_write_preserves_existing_outputs_and_cleans_own_files(self):
        self.ingest()
        before = self.snapshot()
        sibling = Path(self.temp.name) / "unrelated.keep"
        sibling.write_text("preserve")
        with mock.patch.object(self.ingestion, "_write_parquet", side_effect=OSError("injected write failure")):
            with self.assertRaisesRegex(OSError, "injected write failure"):
                self.ingest(force=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(sibling.read_text(), "preserve")
        self.assertFalse((self.fixture.output.parent / ".output.lock").exists())
        self.assertFalse(list(self.fixture.output.parent.glob(".output.staging-*")))
        self.assertEqual(self.ingest()["status"], "cached")

    def test_publication_uses_atomic_replace_and_manifest_last(self):
        replacements = []
        original_replace = self.ingestion.os.replace

        def recording_replace(source, destination, *args, **kwargs):
            destination = Path(destination)
            if destination.parent == self.fixture.output:
                replacements.append(destination.name)
            return original_replace(source, destination, *args, **kwargs)

        with mock.patch.object(self.ingestion.os, "replace", side_effect=recording_replace):
            self.ingest()
        self.assertEqual(set(replacements), set(OUTPUT_NAMES))
        self.assertEqual(replacements[-1], "manifest.json")

    def test_interrupted_publication_cannot_be_accepted_as_complete_cache(self):
        self.ingest()
        before = self.snapshot()
        # This represents a newly pinned fixture source, not an unverified
        # production override. Ensure old and new sample output bytes differ.
        self.fixture.samples[0][1] = "7777.0"
        self.fixture.write()
        original_replace = self.ingestion.os.replace

        def interrupt_before_manifest(source, destination, *args, **kwargs):
            if Path(destination) == self.fixture.output / "manifest.json":
                raise OSError("injected interruption before manifest publication")
            return original_replace(source, destination, *args, **kwargs)

        with mock.patch.object(self.ingestion.os, "replace", side_effect=interrupt_before_manifest):
            with self.assertRaisesRegex(OSError, "injected interruption"):
                self.ingest()
        # Per-file publication may leave new data with the previous manifest.
        # The contract promises detection/rebuild, not a directory transaction.
        self.assertEqual(sha256(self.fixture.output / "manifest.json"), before["manifest.json"][0])
        self.assertNotEqual(sha256(self.fixture.output / "samples.parquet"), before["samples.parquet"][0])
        self.assertFalse((self.fixture.output.parent / ".output.lock").exists())
        self.assertFalse(list(self.fixture.output.parent.glob(".output.staging-*")))
        self.assertEqual(self.ingest()["status"], "built")
        records = pq.read_table(self.fixture.output / "samples.parquet").to_pylist()
        changed = next(r for r in records if r["source_row_number"] == 1)
        self.assertEqual(changed["aeration_rate"], 7777.0)
        self.assertEqual(self.ingest()["status"], "cached")

    def test_held_writer_lock_is_not_deleted_by_other_invocation(self):
        lock = self.fixture.output.parent / ".output.lock"
        lock.write_text("some other invocation owns this lock")
        with self.assertRaises((RuntimeError, OSError)):
            self.ingest()
        self.assertEqual(lock.read_text(), "some other invocation owns this lock")
        self.assertFalse((self.fixture.output / "manifest.json").exists())

    def test_public_cli_rejects_fixture_under_pinned_production_contract(self):
        command = [sys.executable, str(SCRIPT), "--archive", str(self.fixture.archive),
                   "--output-dir", str(self.fixture.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.fixture.output / "manifest.json").exists())
        self.assertIn("error", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
