"""Actual Neo4j, processed-data and Streamlit AppTest demo acceptance.

AppTest executes the real UI script without a browser. Mocked failure checks
below are explicitly marked and do not substitute for the successful live path.
"""
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from .test_demo import app_text
except ImportError:
    from test_demo import app_text
from scripts import graph, investigation


@unittest.skipUnless(os.environ.get("PHARMAGRAPH_NEO4J_INTEGRATION") == "1",
                     "Requires real local Neo4j, verified processed data and PHARMAGRAPH_NEO4J_INTEGRATION=1")
class DemoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = importlib.import_module("scripts.demo")
        cls.database = graph.environment().get("NEO4J_DATABASE", "neo4j")
        cls.driver = graph.driver_from_env()
        cls.addClassCleanup(cls.driver.close)
        cls.driver.verify_connectivity()
        cls.bundle = graph.validate_processed(graph.DEFAULT_OUTPUT)
        cls.dataset_id = cls.bundle["manifest"]["dataset"]["id"]
        cls.results = {ref: investigation.investigate_batch(cls.driver, f"{cls.dataset_id}:batch:{ref:03d}",
            database=cls.database) for ref in (1, 31, 91)}

    def new_app(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_data.clear()
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        app.session_state["page_navigation"] = "Investigate a batch"
        return app

    def assert_healthy_app(self, app):
        self.assertFalse(app.exception, [str(e.value) for e in app.exception])
        self.assertFalse(app.error, app_text(app))

    def test_actual_trends_four_approved_variables_and_graph_provenance_edges(self):
        batches = self.demo.live_context(self.driver, self.bundle, self.database)
        self.assertEqual(len(batches), 100)
        trends = self.demo.load_trends(self.driver, self.bundle, f"{self.dataset_id}:batch:031", self.database)
        self.assertEqual(set(trends["references"]), set(investigation.DEFAULT_VARIABLES))
        self.assertEqual(set(trends["measurements"]), set(investigation.DEFAULT_VARIABLES))
        reference = trends["references"]["temperature"]
        self.assertEqual(reference["unit_reported"], "K")
        row = next(row for row in trends["measurements"]["temperature"] if row["time_tick"] == 430)
        self.assertEqual((row["source_row_number"], reference["source_column_index"]), (34755, 17))
        self.assertAlmostEqual(row["value"], 298.38)
        edges = self.demo.graph_provenance(self.driver, reference, self.database)
        actual = {(r["from_label"], r["from_id"], r["relationship"], r["to_label"], r["to_id"]) for r in edges}
        expected = {
            ("Batch", reference["batch_id"], "HAS_DATA", "ProcessedArtifact", reference["artifact_id"]),
            ("Variable", reference["variable_id"], "HAS_DATA", "ProcessedArtifact", reference["artifact_id"]),
            ("Variable", reference["variable_id"], "FROM_SOURCE", "SourceFile", reference["source_file_id"]),
            ("ProcessedArtifact", reference["artifact_id"], "DERIVED_FROM", "SourceFile", reference["source_file_id"])}
        self.assertTrue(expected <= actual, edges)
        for label_a, id_a, relationship, label_b, id_b in actual:
            with self.driver.session(database=self.database) as session:
                found = session.execute_read(lambda tx: list(tx.run(
                    "MATCH (a {dataset_id: $dataset_id})-[r]->(b {dataset_id: $dataset_id}) "
                    "WHERE $label_a IN labels(a) AND $label_b IN labels(b) AND type(r)=$relationship "
                    "AND $id_a IN [a.batch_id,a.variable_id,a.artifact_id,a.source_file_id] "
                    "AND $id_b IN [b.batch_id,b.variable_id,b.artifact_id,b.source_file_id] RETURN count(r) AS count",
                    dataset_id=self.dataset_id, label_a=label_a, label_b=label_b,
                    relationship=relationship, id_a=id_a, id_b=id_b)))
            self.assertGreater(found[0]["count"], 0)

    def test_actual_plotting_context_reuses_scorer_and_download_matches_current_engine(self):
        result = self.results[31]
        self.assertEqual(len(result["findings"]), 1)
        finding = result["findings"][0]
        self.assertEqual((finding["variable"], finding["start_tick"], finding["end_tick"]), ("temperature", 430, 435))
        with mock.patch.object(investigation, "investigate_batch", side_effect=AssertionError("Full investigation rerun")), \
             mock.patch.object(investigation, "score_variable", wraps=investigation.score_variable) as scoring:
            points = self.demo.plotting_points(self.driver, self.bundle, result, finding, self.database)
        self.assertEqual(scoring.call_count, 1)
        point = next(point for point in points if point["time_tick"] == 430)
        self.assertAlmostEqual(point["observed_value"], 298.38)
        self.assertAlmostEqual(point["reference_median"], 297.99)
        self.assertEqual(point["source_row_number"], 34755)
        figure = self.demo.finding_figure(finding, points, result["configuration"]["threshold"], "K")
        traces = {trace.name: trace for trace in figure.data}
        index = next(i for i, p in enumerate(points) if p["time_tick"] == 430)
        self.assertAlmostEqual(traces["Upper statistical reference"].y[index], point["reference_median"] + 6 * point["reference_spread"])
        self.assertAlmostEqual(traces["Lower statistical reference"].y[index], point["reference_median"] - 6 * point["reference_spread"])
        self.assertEqual(self.demo.canonical_json_bytes(result),
                         (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
        self.assertEqual(self.demo.result_state(self.results[1])["kind"], "no_findings")
        self.assertEqual(self.demo.result_state(self.results[91])["kind"], "undocumented")

    def test_live_app_complete_flow_explicit_run_no_automatic_rerun_and_exact_download_payload(self):
        import streamlit as st
        engine_call = investigation.investigate_batch
        with mock.patch.object(investigation, "investigate_batch", wraps=engine_call) as engine, \
             mock.patch.object(st, "download_button", wraps=st.download_button) as downloads:
            app = self.new_app().run()
            self.assert_healthy_app(app)
            self.assertEqual(engine.call_count, 0)
            self.assertEqual(len(app.selectbox(key="batch_selector").options), 100)
            self.assertEqual(app.selectbox(key="batch_selector").index, 30)
            self.assertEqual(len(app.get("plotly_chart")), 4)
            app.button(key="run_investigation").click().run()
            self.assert_healthy_app(app)
            self.assertEqual(engine.call_count, 1)
            result = app.session_state["investigation_result"]
            self.assertEqual(result, self.results[31])
            self.assertTrue(app.selectbox(key="finding_selector"))
            self.assertTrue(app.download_button(key="download_investigation"))
            self.assertTrue(downloads.called)
            payloads = [call.kwargs.get("data", call.args[1] if len(call.args) > 1 else None)
                        for call in downloads.call_args_list]
            self.assertIn(self.demo.canonical_json_bytes(self.results[31]), payloads)
            evidence_tables = [frame.value for frame in app.dataframe if "source_row_number" in frame.value.columns]
            self.assertTrue(evidence_tables)
            evidence = next(frame for frame in evidence_tables if "observed_value" in frame.columns)
            self.assertEqual((int(evidence.iloc[0]["source_row_number"]), int(evidence.iloc[0]["source_column_index"])), (34755, 17))
            app.selectbox(key="finding_selector").select_index(0).run()
            app.run()
            self.assert_healthy_app(app)
            self.assertEqual(engine.call_count, 1)
            app.download_button(key="download_investigation").click().run()
            self.assertEqual(engine.call_count, 1)
            app.selectbox(key="batch_selector").select_index(0).run()
            self.assert_healthy_app(app)
            self.assertEqual(engine.call_count, 1)
            self.assertFalse(app.download_button)
            app.button(key="run_investigation").click().run()
            self.assert_healthy_app(app)
            self.assertEqual(engine.call_count, 2)
            self.assertEqual(app.session_state["investigation_result"], self.results[1])
            self.assertIn("not proof", app_text(app).lower())
            app.selectbox(key="batch_selector").select_index(90).run()
            self.assertEqual(engine.call_count, 2)
            self.assertFalse(app.download_button)
            app.button(key="run_investigation").click().run()
            self.assert_healthy_app(app)
            self.assertEqual(engine.call_count, 3)
            self.assertEqual(app.session_state["investigation_result"], self.results[91])
            text = app_text(app).lower()
            self.assertTrue("not assessed" in text or "undocumented" in text)
            self.assertFalse(app.success)

    def test_live_graph_health_check_precedes_cached_result_and_masks_injected_credentials(self):
        from neo4j.exceptions import ServiceUnavailable
        app = self.new_app().run()
        app.button(key="run_investigation").click().run()
        self.assert_healthy_app(app)
        self.assertTrue(app.download_button)
        with mock.patch.object(self.demo, "live_context", side_effect=ServiceUnavailable(
                "Synthetic failure bolt://username:never-display-this-secret@127.0.0.1:7687")), \
             mock.patch.object(investigation, "investigate_batch", side_effect=AssertionError("Unexpected rerun")):
            app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse(app.download_button)
        text = app_text(app)
        self.assertNotIn("never-display-this-secret", text)
        self.assertNotIn("bolt://username", text)
        self.assertNotIn("Traceback", text)

    def test_incompatible_graph_version_has_actionable_error_separate_from_connection_failure(self):
        from neo4j.exceptions import ServiceUnavailable
        app = self.new_app().run()
        self.assert_healthy_app(app)
        with mock.patch.object(self.demo, "live_context", side_effect=ValueError("Synthetic graph manifest/model mismatch")):
            app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        incompatible = " ".join(error.value for error in app.error).lower()
        self.assertTrue(any(word in incompatible for word in ("version", "incompatible", "rebuild", "reload")), incompatible)
        with mock.patch.object(self.demo, "live_context", side_effect=ServiceUnavailable("Synthetic offline")):
            app.run()
        self.assertFalse(app.exception)
        offline = " ".join(error.value for error in app.error).lower()
        self.assertNotEqual(incompatible, offline)

    def test_changed_processed_bytes_invalidate_cached_result_and_do_not_invoke_engine(self):
        with tempfile.TemporaryDirectory(prefix="pharmagraph-demo-cache-test-") as directory:
            root = Path(directory) / "processed"
            shutil.copytree(graph.DEFAULT_OUTPUT, root)
            with mock.patch.dict(os.environ, {"PHARMAGRAPH_PROCESSED_DIR": str(root)}):
                app = self.new_app().run()
                self.assert_healthy_app(app)
                app.button(key="run_investigation").click().run()
                self.assert_healthy_app(app)
                self.assertTrue(app.download_button)
                path = root / "samples.parquet"
                raw = path.read_bytes()
                path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
                with mock.patch.object(investigation, "investigate_batch", side_effect=AssertionError("Unexpected rerun")):
                    app.run()
                self.assertFalse(app.exception)
                self.assertTrue(app.error)
                self.assertFalse(app.download_button)


if __name__ == "__main__":
    unittest.main()
