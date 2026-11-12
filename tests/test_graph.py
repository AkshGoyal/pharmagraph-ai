"""Independent processed-only graph fixtures and offline validation tests.

The tiny fixture is synthetic, has its own identity, and never reads or creates
an archive. Exact schemas and source-column definitions derive from the pinned
contract; manifest structure derives from the recorded processed metadata.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import graph


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def rewrite_identity(value, original, replacement):
    if isinstance(value, str):
        return value.replace(original, replacement)
    if isinstance(value, list):
        return [rewrite_identity(v, original, replacement) for v in value]
    if isinstance(value, dict):
        return {k: rewrite_identity(v, original, replacement) for k, v in value.items()}
    return value


class ProcessedFixture:
    """Schema-complete two-batch bundle, independent of ingestion code."""

    def __init__(self, directory, dataset_id=None):
        self.root = Path(directory)
        self.output = self.root / "processed"
        self.output.mkdir(parents=True)
        self.contract_path = self.root / "fixture_contract.json"
        self.dataset_id = dataset_id or "test:synthetic-graph:" + uuid.uuid4().hex
        contract = json.loads((ROOT / "config/indpensim_contract.json").read_text())
        original_id = contract["dataset"]["id"]
        self.contract = rewrite_identity(contract, original_id, self.dataset_id)
        self.contract["dataset"].update(name="Synthetic processed-only graph fixture",
                                        repository_id="synthetic", doi="test:no-doi",
                                        url="https://example.invalid/graph-fixture")
        self.contract["source"].update(archive_filename="synthetic-no-archive.zip", expected_bytes=1,
                                       expected_sha256="1" * 64, expected_batch_refs=[1, 91])
        for member, count in zip(self.contract["source"]["members"], (2, 6)):
            member.update(expected_rows=count, expected_bytes=1, expected_crc32="00000000")
        self.contract_path.write_text(json.dumps(self.contract, indent=2) + "\n")
        self.rows = {"batches": [], "samples": [], "variables": []}
        for position, ref in enumerate((1, 91)):
            batch_id = f"{self.dataset_id}:batch:{ref:03d}"
            self.rows["batches"].append({
                "dataset_id": self.dataset_id, "batch_id": batch_id, "batch_ref": ref,
                "source_file_id": self.dataset_id + ":statistics", "source_row_number": position + 1,
                "fault_present": ref == 91, "control_regime": "recipe_driven" if ref == 1 else "not_documented",
                "harvest_during_batch_raw": float(ref * 100), "harvest_end_of_batch_raw": float(ref * 200),
                "harvest_total_raw": float(ref * 300), "sample_count": 3, "time_start_h": 0.2, "time_end_h": 0.6,
                "timeseries_first_source_row": position * 3 + 1, "timeseries_last_source_row": position * 3 + 3})
            for tick in (1, 2, 3):
                row = {"dataset_id": self.dataset_id, "batch_id": batch_id, "batch_ref": ref,
                       "sample_id": batch_id + f":tick:{tick:06d}", "source_file_id": self.dataset_id + ":timeseries",
                       "source_row_number": position * 3 + tick, "time_h": tick / 5, "time_tick": tick,
                       "fault_reference_raw": int(ref == 91 and tick == 2), "control_reference_raw": 0,
                       "metadata_33_raw": 1, "metadata_34_raw": ref, "batch_fault_flag_raw": int(ref == 91)}
                for variable in self.contract["variables"]:
                    if variable["output_table"] == "samples":
                        row[variable["output_column"]] = (None if variable["measurement_kind"] == "offline_sparse"
                                                        and tick == 1 else ref + tick / 10 + variable["source_column_index"] / 100)
                self.rows["samples"].append(row)
        self.rows["variables"] = [{"dataset_id": self.dataset_id, **v} for v in self.contract["variables"]]
        self.manifest = rewrite_identity(json.loads((ROOT / "docs/evidence/indpensim/ingestion_manifest.json").read_text()),
                                         original_id, self.dataset_id)
        self.manifest["dataset"] = copy.deepcopy(self.contract["dataset"])
        self.manifest["source"] = {"archive_filename": "synthetic-no-archive.zip", "bytes": 1, "sha256": "1" * 64,
            "members": [{"source_file_id": m["source_file_id"], "path": m["path"], "bytes": m["expected_bytes"],
                         "crc32": m["expected_crc32"], "rows": m["expected_rows"],
                         "header_fields": len(m["expected_header"]), "row_fields": m["expected_row_width"]}
                        for m in self.contract["source"]["members"]]}
        self.manifest["cache_inputs"] = {"archive_sha256": "1" * 64, "contract_sha256": sha256(self.contract_path),
                                          "normalizer_sha256": "2" * 64, "python_version": "3.9.historical-fixture",
                                          "pyarrow_version": "0.0.historical-fixture"}
        self.manifest["cache_key"] = canonical_hash(self.manifest["cache_inputs"])
        self.manifest["outputs"] = {}
        for name in self.rows:
            self.write_table(name)

    def schema(self, name):
        return pa.schema([pa.field(f["name"], pa.type_for_alias(f["type"]), nullable=f["nullable"])
                          for f in self.contract["schemas"][name]])

    def write_manifest(self):
        (self.output / "manifest.json").write_text(json.dumps(self.manifest, sort_keys=True, indent=2) + "\n")

    def write_table(self, name, table=None):
        table = table if table is not None else pa.Table.from_pylist(self.rows[name], schema=self.schema(name))
        filename = name + ".parquet"
        path = self.output / filename
        pq.write_table(table, path, compression="zstd", use_dictionary=False, version="2.6")
        self.manifest["outputs"][filename] = {"bytes": path.stat().st_size, "sha256": sha256(path),
            "rows": table.num_rows, "schema": self.contract["schemas"][name]}
        self.write_manifest()

    def reference(self, batch_ref=91, variable="aeration_rate"):
        b = next(b for b in self.rows["batches"] if b["batch_ref"] == batch_ref)
        v = next(v for v in self.rows["variables"] if v["output_column"] == variable)
        filename = v["output_table"] + ".parquet"
        output = self.manifest["outputs"][filename]
        source = next(s for s in self.manifest["source"]["members"] if s["source_file_id"] == v["source_file_id"])
        return {**v, **{k: b[k] for k in ("batch_id", "batch_ref", "sample_count", "time_start_h", "time_end_h",
                                         "timeseries_first_source_row", "timeseries_last_source_row")},
            "source_row_number": b["source_row_number"] if v["output_table"] == "batches" else None,
            "artifact_id": f"{self.dataset_id}:artifact:{filename}:sha256:{output['sha256']}",
            "artifact_filename": filename, "artifact_sha256": output["sha256"], "source_member_path": source["path"],
            "source_archive_sha256": self.manifest["source"]["sha256"],
            "manifest_sha256": sha256(self.output / "manifest.json"), "cache_key": self.manifest["cache_key"]}


class GraphBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pharmagraph-graph-tests-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = ProcessedFixture(self.temp.name)

    def validate(self):
        return graph.validate_processed(self.fixture.output, self.fixture.contract_path)

    def resolve(self, reference=None, **kwargs):
        return graph.resolve_reference(reference or self.fixture.reference(), self.fixture.output,
                                       contract_path=self.fixture.contract_path, **kwargs)

    def test_complete_schema_bundle_and_historical_writer_are_accepted_without_archive(self):
        bundle = self.validate()
        self.assertEqual(bundle["manifest_sha256"], sha256(self.fixture.output / "manifest.json"))
        for name, count in (("batches", 2), ("samples", 6), ("variables", 33)):
            self.assertEqual(bundle["tables"][name].schema, self.fixture.schema(name))
            self.assertEqual(bundle["tables"][name].num_rows, count)
        self.assertEqual(list(self.fixture.root.glob("*.zip")), [])

    def test_missing_and_corrupt_artifacts_rejected(self):
        path = self.fixture.output / "samples.parquet"
        original = path.read_bytes()
        for damaged in (b"", original[:-1], bytes([original[0] ^ 1]) + original[1:]):
            with self.subTest(size=len(damaged)):
                path.write_bytes(damaged)
                with self.assertRaises(ValueError):
                    self.validate()
        path.unlink()
        with self.assertRaises(ValueError):
            self.validate()

    def test_rehashed_wrong_schema_is_still_rejected(self):
        self.fixture.write_table("samples", pq.read_table(self.fixture.output / "samples.parquet").drop(["aeration_rate"]))
        with self.assertRaises(ValueError):
            self.validate()

    def test_rehashed_wrong_dataset_is_still_rejected(self):
        self.fixture.rows["samples"][0]["dataset_id"] = "test:wrong-dataset"
        self.fixture.write_table("samples")
        with self.assertRaises(ValueError):
            self.validate()

    def test_rehashed_duplicate_sample_ids_and_wrong_batch_joins_rejected(self):
        for key, wrong in (("sample_id", self.fixture.rows["samples"][1]["sample_id"]),
                           ("batch_id", self.fixture.rows["batches"][0]["batch_id"]),
                           ("source_file_id", self.fixture.dataset_id + ":statistics")):
            with self.subTest(key=key):
                original = self.fixture.rows["samples"][3][key]
                self.fixture.rows["samples"][3][key] = wrong
                self.fixture.write_table("samples")
                with self.assertRaises(ValueError):
                    self.validate()
                self.fixture.rows["samples"][3][key] = original

    def test_rehashed_variable_provenance_and_batch_summaries_rejected(self):
        self.fixture.rows["variables"][0]["source_column_index"] = 31
        self.fixture.write_table("variables")
        with self.assertRaises(ValueError):
            self.validate()
        self.fixture.rows["variables"][0]["source_column_index"] = 1
        self.fixture.write_table("variables")
        self.fixture.rows["batches"][0]["sample_count"] = 4
        self.fixture.write_table("batches")
        with self.assertRaises(ValueError):
            self.validate()

    def test_manifest_cache_source_contract_and_output_entries_are_pinned(self):
        original = copy.deepcopy(self.fixture.manifest)
        mutations = (
            lambda m: m.update(cache_key="0" * 64),
            lambda m: m["source"].update(sha256="0" * 64),
            lambda m: m["cache_inputs"].update(contract_sha256="0" * 64),
            lambda m: m["outputs"].update({"../samples.parquet": m["outputs"].pop("samples.parquet")}),
            lambda m: m["outputs"]["samples.parquet"].update(rows=5),
        )
        for mutate in mutations:
            self.fixture.manifest = copy.deepcopy(original)
            mutate(self.fixture.manifest)
            self.fixture.write_manifest()
            with self.subTest(manifest=self.fixture.manifest), self.assertRaises(ValueError):
                self.validate()

    def test_malformed_manifest_containers_are_rejected(self):
        original = copy.deepcopy(self.fixture.manifest)
        invalid = [[], None, "not-a-manifest", {**original, "cache_inputs": []},
                   {**original, "outputs": []}, {**original, "source": []}]
        for value in invalid:
            (self.fixture.output / "manifest.json").write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate()

    def test_resolve_measurements_exact_values_source_rows_and_detector_allowlist(self):
        result = self.resolve(start_tick=1, end_tick=3)
        self.assertEqual([r["value"] for r in result["measurements"]], [91.11, 91.21000000000001, 91.31])
        self.assertEqual([r["source_row_number"] for r in result["measurements"]], [4, 5, 6])
        self.assertEqual([r["time_tick"] for r in result["measurements"]], [1, 2, 3])
        for row in result["measurements"]:
            self.assertEqual(set(row), {"sample_id", "batch_id", "time_h", "time_tick", "value",
                                        "source_file_id", "source_row_number"})
            source = self.fixture.rows["samples"][row["source_row_number"] - 1]
            self.assertEqual(row["sample_id"], source["sample_id"])
            self.assertEqual(row["value"], source["aeration_rate"])

    def test_sparse_nulls_inclusive_ticks_full_batch_and_limit(self):
        self.assertEqual(len(self.resolve()["measurements"]), 3)
        self.assertEqual([r["time_tick"] for r in self.resolve(start_tick=2, end_tick=2)["measurements"]], [2])
        self.assertEqual(len(self.resolve(limit=1)["measurements"]), 1)
        result = self.resolve(self.fixture.reference(variable="paa_offline"))
        self.assertIsNone(result["measurements"][0]["value"])
        self.assertEqual(len(result["measurements"]), 3)

    def test_summary_reference_has_statistics_provenance_and_no_tick_coordinates(self):
        reference = self.fixture.reference(variable="harvest_total_raw")
        result = self.resolve(reference)
        self.assertEqual(reference["source_row_number"], 2)
        self.assertEqual(result["measurements"], [{"batch_id": reference["batch_id"], "value": 27300.0,
            "source_file_id": self.fixture.dataset_id + ":statistics", "source_row_number": 2}])
        with self.assertRaises(ValueError):
            self.resolve(reference, start_tick=1)

    def test_tampered_reference_never_selects_another_batch_artifact_or_metadata(self):
        for key, value in (("batch_id", self.fixture.rows["batches"][0]["batch_id"]), ("batch_ref", 1),
                           ("artifact_filename", "../samples.parquet"), ("artifact_sha256", "0" * 64),
                           ("manifest_sha256", "0" * 64), ("cache_key", "0" * 64), ("source_row_number", 4),
                           ("source_column_index", 31), ("output_column", "fault_reference_raw"),
                           ("unit_reported", "invented"), ("fault_present", True)):
            reference = self.fixture.reference()
            reference[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.resolve(reference)

    def test_changed_intact_bundle_invalidates_old_reference(self):
        old = self.fixture.reference()
        self.fixture.rows["samples"][3]["aeration_rate"] = 999.25
        self.fixture.write_table("samples")
        self.validate()
        with self.assertRaises(ValueError):
            self.resolve(old)
        self.assertEqual(self.resolve()["measurements"][0]["value"], 999.25)

    def test_tick_and_limit_types_are_not_coerced(self):
        cases = ({"start_tick": True}, {"end_tick": 1.1}, {"limit": "2"}, {"limit": 0},
                 {"start_tick": -1}, {"limit": -1}, {"start_tick": 3, "end_tick": 2})
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.resolve(**kwargs)

    def test_dotenv_is_data_only_and_environment_overrides_file(self):
        path = self.fixture.root / "test.env"
        path.write_text("# comment\nNEO4J_USER='fixture-user'\nNEO4J_PASSWORD=\"literal-$(echo no)\"\n")
        with mock.patch.dict(os.environ, {"NEO4J_USER": "environment-user"}):
            values = graph.environment(path)
        self.assertEqual(values["NEO4J_USER"], "environment-user")
        self.assertEqual(values["NEO4J_PASSWORD"], "literal-$(echo no)")


if __name__ == "__main__":
    unittest.main()
