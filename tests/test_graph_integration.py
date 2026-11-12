"""Actual Neo4j behavior; opt in with PHARMAGRAPH_NEO4J_INTEGRATION=1.

Requires the pinned neo4j driver, a running local instance and NEO4J_PASSWORD
in the environment/repo .env. No mock is used as database acceptance evidence.
Every test creates random, distinct synthetic dataset IDs and deletes only its
own nodes. No production dataset is loaded, modified or cleared by these tests.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from .test_graph import ProcessedFixture
except ImportError:
    from test_graph import ProcessedFixture
from scripts import graph


@unittest.skipUnless(os.environ.get("PHARMAGRAPH_NEO4J_INTEGRATION") == "1",
                     "Requires real local Neo4j and PHARMAGRAPH_NEO4J_INTEGRATION=1 with NEO4J_PASSWORD")
class GraphIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = graph.environment().get("NEO4J_DATABASE", "neo4j")
        cls.driver = graph.driver_from_env()
        cls.driver.verify_connectivity()

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pharmagraph-live-graph-tests-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = ProcessedFixture(self.temp.name)
        self.dataset_ids = [self.fixture.dataset_id]
        self.addCleanup(self.cleanup_datasets)
        self.load()

    def cleanup_datasets(self):
        with self.driver.session(database=self.database) as session:
            session.execute_write(lambda tx: tx.run(
                "MATCH (n) WHERE n.dataset_id IN $dataset_ids DETACH DELETE n", dataset_ids=self.dataset_ids).consume())

    def query(self, query, **parameters):
        with self.driver.session(database=self.database) as session:
            return session.execute_read(lambda tx: [r.data() for r in tx.run(query, **parameters)])

    def write(self, query, **parameters):
        with self.driver.session(database=self.database) as session:
            session.execute_write(lambda tx: tx.run(query, **parameters).consume())

    def load(self, *, replace=False, fixture=None):
        fixture = fixture or self.fixture
        return graph.load_graph(self.driver, fixture.output, database=self.database,
                                batch_size=7, replace=replace, contract_path=fixture.contract_path)

    def counts(self):
        return graph.graph_counts(self.driver, self.fixture.dataset_id, self.database)

    def reference(self, variable="aeration_rate", detector_only=True):
        return graph.get_reference(self.driver, self.fixture.dataset_id, 91, variable,
                                   self.database, detector_only)

    def resolve(self, reference, **kwargs):
        return graph.resolve_reference(reference, self.fixture.output, contract_path=self.fixture.contract_path, **kwargs)

    def test_double_load_has_exact_counts_stable_ids_and_complete_structure(self):
        first = self.counts()
        identities_before = self.query("MATCH (n {dataset_id: $dataset_id}) RETURN labels(n) AS labels, "
            "coalesce(n.annotation_id, n.artifact_id, n.variable_id, n.batch_id, n.source_file_id, n.dataset_id) AS id "
            "ORDER BY labels, id", dataset_id=self.fixture.dataset_id)
        second = self.load()
        self.assertEqual(first, second["actual_counts"])
        self.assertEqual(first["nodes"], {"Dataset": 1, "SourceFile": 2, "ProcessedArtifact": 3,
                                         "Batch": 2, "Variable": 33, "FaultAnnotation": 2})
        self.assertEqual(first["relationships"], {"HAS_SOURCE": 2, "HAS_ARTIFACT": 3, "HAS_BATCH": 2,
            "HAS_VARIABLE": 33, "FROM_SOURCE": 37, "HAS_DATA": 37, "DERIVED_FROM": 4, "HAS_ANNOTATION": 2})
        self.assertEqual((first["total_nodes"], first["total_relationships"]), (43, 120))
        identities_after = self.query("MATCH (n {dataset_id: $dataset_id}) RETURN labels(n) AS labels, "
            "coalesce(n.annotation_id, n.artifact_id, n.variable_id, n.batch_id, n.source_file_id, n.dataset_id) AS id "
            "ORDER BY labels, id", dataset_id=self.fixture.dataset_id)
        self.assertEqual(identities_before, identities_after)
        integrity = graph.check_graph_integrity(self.driver, self.fixture.dataset_id, self.database)
        self.assertTrue(integrity["ok"], integrity)
        self.assertFalse(any(integrity["duplicate_ids"].values()))
        self.assertFalse(any(integrity["missing_relationships"].values()))

    def test_uniqueness_constraints_are_installed_and_enforced(self):
        rows = self.query("SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type RETURN labelsOrTypes, properties, type")
        for label, key in (("Dataset", "dataset_id"), ("SourceFile", "source_file_id"),
                           ("ProcessedArtifact", "artifact_id"), ("Batch", "batch_id"),
                           ("Variable", "variable_id"), ("FaultAnnotation", "annotation_id")):
            self.assertTrue(any(label in r["labelsOrTypes"] and key in r["properties"]
                                and "UNIQUENESS" in r["type"] for r in rows), (label, rows))
        from neo4j.exceptions import ConstraintError
        with self.assertRaises(ConstraintError):
            self.write("CREATE (:Batch {dataset_id: $dataset_id, batch_id: $batch_id})",
                       dataset_id=self.fixture.dataset_id, batch_id=self.fixture.rows["batches"][0]["batch_id"])
        self.assertEqual(self.counts()["nodes"]["Batch"], 2)

    def test_graph_reference_resolves_actual_values_source_rows_and_separate_annotations(self):
        reference = self.reference()
        self.assertEqual(reference, self.fixture.reference())
        result = self.resolve(reference, start_tick=2, end_tick=3)
        self.assertEqual([r["source_row_number"] for r in result["measurements"]], [5, 6])
        for row in result["measurements"]:
            raw = self.fixture.rows["samples"][row["source_row_number"] - 1]
            self.assertEqual((row["sample_id"], row["batch_id"], row["value"]),
                             (raw["sample_id"], raw["batch_id"], raw["aeration_rate"]))
        self.assertEqual(reference["source_column_index"], 1)
        self.assertEqual(reference["source_file_id"], self.fixture.dataset_id + ":timeseries")
        annotations = graph.published_annotations(self.driver, self.fixture.dataset_id, database=self.database)
        self.assertEqual([(r["batch_ref"], r["fault_present"]) for r in annotations], [(1, False), (91, True)])
        self.assertTrue(all(r["source_column_index"] == 4 for r in annotations))
        self.assertEqual(len(graph.published_annotations(self.driver, self.fixture.dataset_id, 91, self.database)), 1)

    def test_detector_queries_use_allowlists_and_summary_values_require_opt_in(self):
        batches = graph.list_batches(self.driver, self.fixture.dataset_id, self.database)
        self.assertEqual(len(batches), 2)
        for row in batches:
            self.assertEqual(set(row), {"batch_id", "batch_ref", "sample_count", "time_start_h", "time_end_h"})
        variables = graph.list_variables(self.driver, self.fixture.dataset_id, self.database)
        self.assertEqual(len(variables), 30)
        self.assertTrue(all(v["output_table"] == "samples" for v in variables))
        self.assertEqual(len(graph.list_variables(self.driver, self.fixture.dataset_id, self.database, False)), 33)
        inventory = graph.batch_variables(self.driver, self.fixture.dataset_id, 91, self.database)
        self.assertEqual(len(inventory), 30)
        self.assertEqual(len(graph.batch_variables(self.driver, self.fixture.dataset_id, 91, self.database, False)), 33)
        forbidden = {"fault_present", "fault_reference_raw", "batch_fault_flag_raw", "control_reference_raw",
                     "control_regime", "metadata_33_raw", "metadata_34_raw", "annotation_id", "annotation_kind"}
        for row in batches + variables + inventory + self.resolve(self.reference())["measurements"]:
            self.assertFalse(set(row) & forbidden, row)
        for forbidden_variable in ("fault_present", "fault_reference_raw", "harvest_total_raw", "aeration_rate' OR true //"):
            with self.subTest(variable=forbidden_variable), self.assertRaises(ValueError):
                self.reference(forbidden_variable)
        self.assertEqual(self.reference(self.fixture.dataset_id + ":variable:aeration_rate"), self.reference())
        summary = self.reference("harvest_total_raw", False)
        self.assertEqual(summary["source_row_number"], 2)
        self.assertEqual(summary["source_file_id"], self.fixture.dataset_id + ":statistics")
        self.assertEqual(self.resolve(summary)["measurements"][0]["value"], 27300.0)

    def test_missing_required_edge_is_detected_and_same_manifest_reload_repairs_it(self):
        self.write("MATCH (v:Variable {dataset_id: $dataset_id, output_column: 'aeration_rate'})-[r:HAS_DATA]->() DELETE r",
                   dataset_id=self.fixture.dataset_id)
        integrity = graph.check_graph_integrity(self.driver, self.fixture.dataset_id, self.database)
        self.assertFalse(integrity["ok"])
        self.assertEqual(integrity["missing_relationships"]["HAS_DATA"], 1)
        self.assertEqual(self.counts()["total_relationships"], 119)
        self.load()
        self.assertTrue(graph.check_graph_integrity(self.driver, self.fixture.dataset_id, self.database)["ok"])

    def test_wrong_edge_is_detected_even_with_unchanged_total_count(self):
        self.write("MATCH (v:Variable {dataset_id: $dataset_id, output_column: 'aeration_rate'})-[r:FROM_SOURCE]->() "
                   "MATCH (wrong:SourceFile {source_file_id: $statistics}) DELETE r CREATE (v)-[:FROM_SOURCE]->(wrong)",
                   dataset_id=self.fixture.dataset_id, statistics=self.fixture.dataset_id + ":statistics")
        self.assertEqual(self.counts()["total_relationships"], 120)
        integrity = graph.check_graph_integrity(self.driver, self.fixture.dataset_id, self.database)
        self.assertFalse(integrity["ok"])
        self.assertEqual(integrity["missing_relationships"]["FROM_SOURCE"], 1)

    def test_incomplete_or_unsupported_model_rejects_all_query_helpers(self):
        for properties in ({"load_state": "loading"}, {"load_state": "complete", "graph_model_version": 999}):
            self.write("MATCH (d:Dataset {dataset_id: $dataset_id}) SET d += $properties",
                       dataset_id=self.fixture.dataset_id, properties=properties)
            queries = (
                lambda: graph.list_batches(self.driver, self.fixture.dataset_id, self.database),
                lambda: graph.list_variables(self.driver, self.fixture.dataset_id, self.database),
                lambda: graph.batch_variables(self.driver, self.fixture.dataset_id, 91, self.database),
                lambda: self.reference(),
                lambda: graph.published_annotations(self.driver, self.fixture.dataset_id, database=self.database))
            for query in queries:
                with self.assertRaises(ValueError):
                    query()
        self.load(replace=True)
        self.assertEqual(len(graph.list_batches(self.driver, self.fixture.dataset_id, self.database)), 2)

    def test_changed_manifest_refused_without_changes_and_explicit_replace_is_dataset_scoped(self):
        other = ProcessedFixture(Path(self.temp.name) / "other")
        self.dataset_ids.append(other.dataset_id)
        self.load(fixture=other)
        other_before = graph.graph_counts(self.driver, other.dataset_id, self.database)
        old_reference = self.reference()
        old_counts = self.counts()
        self.fixture.rows["samples"][3]["aeration_rate"] = 777.0
        self.fixture.write_table("samples")
        with self.assertRaises(ValueError):
            self.load()
        self.assertEqual(self.counts(), old_counts)
        self.assertEqual(self.reference(), old_reference)
        with self.assertRaises(ValueError):
            self.resolve(old_reference)
        self.load(replace=True)
        self.assertEqual(self.counts(), old_counts)
        self.assertEqual(graph.graph_counts(self.driver, other.dataset_id, self.database), other_before)
        self.assertEqual(self.resolve(self.reference())["measurements"][0]["value"], 777.0)

    def test_manifest_bytes_are_pinned_even_if_cache_key_is_unchanged(self):
        before = self.reference()
        manifest = self.fixture.output / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.load()
        self.assertEqual(self.reference(), before)
        self.assertEqual(self.counts()["total_nodes"], 43)


if __name__ == "__main__":
    unittest.main()
