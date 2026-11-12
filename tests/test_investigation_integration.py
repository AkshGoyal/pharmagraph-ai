"""Real Neo4j investigation tests using exclusively synthetic fixture datasets."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from .test_investigation import InvestigationFixture, result_bytes
except ImportError:
    from test_investigation import InvestigationFixture, result_bytes
from scripts import graph


@unittest.skipUnless(os.environ.get("PHARMAGRAPH_NEO4J_INTEGRATION") == "1",
                     "Requires real local Neo4j and PHARMAGRAPH_NEO4J_INTEGRATION=1 with NEO4J_PASSWORD")
class InvestigationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = importlib.import_module("scripts.investigation")
        cls.database = graph.environment().get("NEO4J_DATABASE", "neo4j")
        cls.driver = graph.driver_from_env()
        cls.addClassCleanup(cls.driver.close)
        cls.driver.verify_connectivity()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pharmagraph-investigation-tests-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = InvestigationFixture(self.temp.name)
        self.addCleanup(self.cleanup_fixture)
        graph.load_graph(self.driver, self.fixture.output, database=self.database, contract_path=self.fixture.contract_path)
        self.config = self.engine.DetectorConfig(min_peers=3)

    def cleanup_fixture(self):
        with self.driver.session(database=self.database) as session:
            session.execute_write(lambda tx: tx.run("MATCH (n {dataset_id: $dataset_id}) DETACH DELETE n",
                dataset_id=self.fixture.dataset_id).consume())

    def write(self, cypher, **parameters):
        with self.driver.session(database=self.database) as session:
            session.execute_write(lambda tx: tx.run(cypher, **parameters).consume())

    def investigate(self, batch_ref=1, config=None):
        batch_id = f"{self.fixture.dataset_id}:batch:{batch_ref:03d}"
        return self.engine.investigate_batch(self.driver, batch_id, self.fixture.output, database=self.database,
            config=self.config if config is None else config, contract_path=self.fixture.contract_path)

    def test_injected_interval_has_independently_known_score_and_graph_parquet_trace(self):
        result = self.investigate()
        self.assertEqual((result["schema_version"], result["record_kind"]), (1, "derived_investigation"))
        self.assertEqual((result["detector"]["id"], result["detector"]["version"]),
                         ("elapsed_tick_peer_median_mad", "1.0.0"))
        self.assertEqual(len(result["findings"]), 1)
        finding = result["findings"][0]
        self.assertEqual((finding["variable"], finding["start_tick"], finding["end_tick"], finding["point_count"]),
                         ("aeration_rate", 1, 8, 8))
        self.assertAlmostEqual(finding["statistical_deviation_score"], 10.0 / 1.4826)
        self.assertEqual(finding["record_kind"], "derived_statistical_deviation")
        reference = graph.get_reference(self.driver, self.fixture.dataset_id, 1, "aeration_rate", self.database)
        self.assertEqual(reference, self.fixture.reference(1, "aeration_rate"))
        rows = graph.resolve_reference(reference, self.fixture.output, contract_path=self.fixture.contract_path)["measurements"]
        by_tick = {r["time_tick"]: r for r in rows}
        for point in finding["evidence"]:
            actual = by_tick[point["time_tick"]]
            self.assertEqual(point["observed_value"], actual["value"])
            for key in ("batch_id", "sample_id", "source_file_id", "source_row_number"):
                self.assertEqual(point[key], actual[key])
            self.assertEqual((point["reference_median"], point["reference_mad"], point["peer_count"]), (0.0, 1.0, 5))
            for support in point["peer_measurements"]:
                stored = self.fixture.rows["samples"][support["source_row_number"] - 1]
                self.assertEqual((support["sample_id"], support["value"]), (stored["sample_id"], stored["aeration_rate"]))
        self.assertTrue(result["limitations"])
        self.assertEqual(result_bytes(result), result_bytes(self.investigate()))

    def test_actual_graph_annotation_flip_and_removal_leave_complete_result_byte_identical(self):
        with mock.patch.object(graph, "published_annotations", side_effect=AssertionError("Forbidden annotation query")), \
             mock.patch.object(graph, "check_graph_integrity", side_effect=AssertionError("Forbidden global integrity query")):
            before = result_bytes(self.investigate())
            self.write("MATCH (a:FaultAnnotation {dataset_id: $dataset_id}) SET a.fault_present = NOT a.fault_present",
                       dataset_id=self.fixture.dataset_id)
            after_flip = result_bytes(self.investigate())
            self.write("MATCH (a:FaultAnnotation {dataset_id: $dataset_id}) DETACH DELETE a",
                       dataset_id=self.fixture.dataset_id)
            after_removal = result_bytes(self.investigate())
        self.assertEqual(before, after_flip)
        self.assertEqual(before, after_removal)

    def test_known_regime_grouping_excludes_target_and_other_regimes(self):
        result = self.investigate()
        self.assertEqual(result["reference_cohort"]["compatibility_group"], "recipe_driven")
        ids = [m["batch_id"] for m in result["reference_cohort"]["members"]]
        self.assertEqual(ids, [f"{self.fixture.dataset_id}:batch:{ref:03d}" for ref in range(2, 7)])
        self.assertNotIn(self.fixture.rows["batches"][0]["batch_id"], ids)
        self.assertEqual([v["variable"] for v in result["variable_results"]],
                         ["aeration_rate", "sugar_feed_rate", "ph", "temperature"])
        self.assertFalse(set(result["batch"]) & {"fault_present", "control_regime", "fault_reference_raw"})

    def test_restricted_cohort_cannot_override_compatibility_and_unknown_ids_fail(self):
        ids = tuple(f"{self.fixture.dataset_id}:batch:{ref:03d}" for ref in (31, 6, 5, 4, 3, 2, 1))
        restricted = self.engine.DetectorConfig(min_peers=3, peer_batch_ids=ids)
        result = self.investigate(config=restricted)
        members = [m["batch_ref"] for m in result["reference_cohort"]["members"]]
        self.assertEqual(members, [2, 3, 4, 5, 6])
        repeat = self.investigate(config=self.engine.DetectorConfig(min_peers=3, peer_batch_ids=tuple(reversed(ids))))
        self.assertEqual(result_bytes(result), result_bytes(repeat))
        with self.assertRaises(ValueError):
            self.investigate(config=self.engine.DetectorConfig(min_peers=3, peer_batch_ids=("test:unknown-peer",)))

    def test_unknown_process_compatibility_skips_all_variables_without_pooling(self):
        result = self.investigate(91)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["reference_cohort"]["members"], [])
        self.assertTrue(all(v["status"] == "skipped" and v["skipped_reason"] == "undocumented_process_compatibility"
                            for v in result["variable_results"]))

    def test_default_minimum_peers_reports_insufficient_coverage_as_no_scoreable_data(self):
        result = self.investigate(config=self.engine.DetectorConfig())
        self.assertEqual(result["findings"], [])
        for variable in result["variable_results"]:
            self.assertEqual(variable["scored_point_count"], 0)
            self.assertEqual(variable["skipped_tick_counts"]["insufficient_peers"], 8)

    def test_graph_batch_metadata_mismatch_and_unsupported_model_fail_without_fallback(self):
        self.write("MATCH (b:Batch {dataset_id: $dataset_id, batch_ref: 1}) SET b.sample_count = 999",
                   dataset_id=self.fixture.dataset_id)
        with self.assertRaises(ValueError):
            self.investigate()
        self.write("MATCH (b:Batch {dataset_id: $dataset_id, batch_ref: 1}) SET b.sample_count = 8",
                   dataset_id=self.fixture.dataset_id)
        self.write("MATCH (d:Dataset {dataset_id: $dataset_id}) SET d.graph_model_version = 999",
                   dataset_id=self.fixture.dataset_id)
        with self.assertRaises(ValueError):
            self.investigate()

    def test_graph_variable_source_and_artifact_mismatches_fail(self):
        self.write("MATCH (v:Variable {dataset_id: $dataset_id, output_column: 'aeration_rate'}) "
                   "SET v.source_column_index = 999", dataset_id=self.fixture.dataset_id)
        with self.assertRaises(ValueError):
            self.investigate()
        self.write("MATCH (v:Variable {dataset_id: $dataset_id, output_column: 'aeration_rate'}) "
                   "SET v.source_column_index = 1", dataset_id=self.fixture.dataset_id)
        self.write("MATCH (a:ProcessedArtifact {dataset_id: $dataset_id, output_table: 'samples'}) SET a.sha256 = $wrong",
                   dataset_id=self.fixture.dataset_id, wrong="0" * 64)
        with self.assertRaises(ValueError):
            self.investigate()

    def test_missing_selected_variable_is_explicitly_skipped(self):
        self.write("MATCH (:Dataset {dataset_id: $dataset_id})-[r:HAS_VARIABLE]->(:Variable {output_column: 'ph'}) DELETE r",
                   dataset_id=self.fixture.dataset_id)
        result = self.investigate()
        skipped = next(v for v in result["variable_results"] if v["variable"] == "ph")
        self.assertEqual(skipped["status"], "skipped")
        self.assertTrue(skipped["skipped_reason"])

    def test_dataset_pins_checked_even_without_selected_variable_inventory(self):
        self.write("MATCH (:Dataset {dataset_id: $dataset_id})-[r:HAS_VARIABLE]->(v:Variable) "
                   "WHERE v.output_column IN $variables DELETE r",
                   dataset_id=self.fixture.dataset_id, variables=list(self.engine.DEFAULT_VARIABLES))
        valid = self.investigate()
        self.assertTrue(all(v["status"] == "skipped" for v in valid["variable_results"]))
        self.write("MATCH (d:Dataset {dataset_id: $dataset_id}) SET d.manifest_sha256 = $wrong",
                   dataset_id=self.fixture.dataset_id, wrong="0" * 64)
        with self.assertRaisesRegex(ValueError, "dataset pins"):
            self.investigate()

    def test_artifact_pins_checked_even_without_selected_variable_inventory(self):
        self.write("MATCH (:Dataset {dataset_id: $dataset_id})-[r:HAS_VARIABLE]->(v:Variable) "
                   "WHERE v.output_column IN $variables DELETE r",
                   dataset_id=self.fixture.dataset_id, variables=list(self.engine.DEFAULT_VARIABLES))
        self.write("MATCH (a:ProcessedArtifact {dataset_id: $dataset_id, output_table: 'samples'}) "
                   "SET a.sha256 = $wrong", dataset_id=self.fixture.dataset_id, wrong="0" * 64)
        with self.assertRaisesRegex(ValueError, "artifact pins"):
            self.investigate()

    def test_deterministic_variable_order_findings_and_no_bundle_writes(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.fixture.output.iterdir()}
        config = self.engine.DetectorConfig(variables=("temperature", "aeration_rate"), min_peers=3)
        first = self.investigate(config=config)
        second = self.investigate(config=config)
        self.assertEqual(result_bytes(first), result_bytes(second))
        self.assertEqual([v["variable"] for v in first["variable_results"]], ["temperature", "aeration_rate"])
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.fixture.output.iterdir()}
        self.assertEqual(before, after)
        encoded = result_bytes(first)
        self.assertNotIn(str(self.fixture.root).encode(), encoded)
        self.assertNotIn(b"fault_present", encoded)
        self.assertNotIn(b"fault_reference_raw", encoded)

    def test_finding_score_ties_use_configured_variable_order(self):
        for sample in self.fixture.rows["samples"]:
            if sample["batch_ref"] == 1:
                sample["sugar_feed_rate"] = 10.0
        self.fixture.write_table("samples")
        graph.load_graph(self.driver, self.fixture.output, database=self.database,
                         contract_path=self.fixture.contract_path, replace=True)
        config = self.engine.DetectorConfig(variables=("sugar_feed_rate", "aeration_rate"), min_peers=3)
        result = self.investigate(config=config)
        self.assertEqual([f["variable"] for f in result["findings"]], ["sugar_feed_rate", "aeration_rate"])
        self.assertAlmostEqual(result["findings"][0]["statistical_deviation_score"],
                               result["findings"][1]["statistical_deviation_score"])

    def test_scorer_receives_only_selected_measurements_with_source_coordinates(self):
        scorer = self.engine.score_variable
        with mock.patch.object(self.engine, "score_variable", wraps=scorer) as observed:
            self.investigate()
        self.assertEqual(observed.call_count, 4)
        allowed = {"batch_id", "sample_id", "time_tick", "time_h", "value", "source_file_id", "source_row_number"}
        for call in observed.call_args_list:
            targets, peers = call.args[:2]
            for row in list(targets) + [row for rows in peers.values() for row in rows]:
                self.assertEqual(set(row), allowed)
                self.assertTrue(row["source_file_id"].endswith(":timeseries"))
                self.assertGreater(row["source_row_number"], 0)


class InvestigationCliTests(unittest.TestCase):
    def test_invalid_config_does_not_create_or_replace_output(self):
        with tempfile.TemporaryDirectory(prefix="pharmagraph-investigation-cli-") as directory:
            output = Path(directory) / "result.json"
            for exists in (False, True):
                if exists:
                    output.write_bytes(b"existing-result\n")
                result = subprocess.run([sys.executable, str(ROOT / "scripts/investigate_batch.py"),
                    "--batch-id", "test:unknown", "--output", str(output), "--threshold", "nan"],
                    capture_output=True, text=True, cwd=ROOT)
                self.assertNotEqual(result.returncode, 0)
                if exists:
                    self.assertEqual(output.read_bytes(), b"existing-result\n")
                else:
                    self.assertFalse(output.exists())
                error = json.loads(result.stderr)
                self.assertEqual(error["status"], "error")


if __name__ == "__main__":
    unittest.main()
