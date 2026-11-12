"""Independent presentation tests; mocked failure paths are not live acceptance."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def recorded_result(batch="031"):
    return json.loads((ROOT / f"docs/evidence/investigation/batch{batch}.json").read_text())


def app_text(app):
    values = []
    for kind in ("title", "header", "subheader", "markdown", "caption", "info", "warning", "error", "success"):
        values.extend(str(element.value) for element in app.get(kind))
    return "\n".join(values)


class DemoPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = importlib.import_module("scripts.demo")

    def test_download_matches_cli_json_bytes_preserves_unicode_and_never_mutates_engine_result(self):
        result = recorded_result()
        result["limitations"].append("Synthetic presentation Unicode check: µ")
        before = copy.deepcopy(result)
        expected = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        self.assertEqual(self.demo.canonical_json_bytes(result), expected)
        self.assertEqual(json.loads(expected), before)
        self.assertEqual(result, before)
        result["bad_float"] = float("nan")
        with self.assertRaises(ValueError):
            self.demo.canonical_json_bytes(result)

    def test_result_states_distinguish_findings_assessed_none_and_undocumented(self):
        expected = (("031", "findings"), ("001", "no_findings"), ("091", "undocumented"))
        for batch, kind in expected:
            result = recorded_result(batch)
            state = self.demo.result_state(result)
            with self.subTest(batch=batch):
                self.assertEqual(state["kind"], kind)
                self.assertTrue(state["message"])
        no_findings = self.demo.result_state(recorded_result("001"))["message"].lower()
        self.assertIn("not proof", no_findings)
        self.assertTrue("safe" in no_findings or "normal" in no_findings)

    def test_unscoreable_coverage_is_distinct_from_no_findings_and_partial_skips_visible(self):
        result = recorded_result("001")
        for variable in result["variable_results"]:
            variable.update(scored_point_count=0, status="skipped", skipped_reason="insufficient_peer_coverage",
                            skipped_tick_counts={"insufficient_peers": 3}, skipped_ticks=[])
        state = self.demo.result_state(result)
        self.assertEqual(state["kind"], "unscorable")
        self.assertEqual(state["skipped_tick_count"], 12)
        actual = recorded_result("031")
        partial = self.demo.result_state(actual)
        self.assertEqual(partial["kind"], "findings")
        self.assertEqual(partial["skipped_tick_count"], sum(sum(v["skipped_tick_counts"].values())
                                                          for v in actual["variable_results"]))
        self.assertGreater(partial["skipped_tick_count"], 0)

    def test_zero_mad_unscoreable_is_visible_as_unassessed_coverage(self):
        result = recorded_result("001")
        for variable in result["variable_results"]:
            variable.update(scored_point_count=0, status="skipped", skipped_reason="no_scoreable_ticks",
                            skipped_tick_counts={"zero_mad_unscorable": 5},
                            skipped_ticks=[{"time_tick": tick, "status": "zero_mad_unscorable"} for tick in range(1, 6)])
        state = self.demo.result_state(result)
        self.assertEqual(state["kind"], "unscorable")
        self.assertEqual(state["skipped_tick_count"], 20)
        self.assertNotEqual(state["kind"], "no_findings")

    def test_evidence_rows_bind_all_interval_points_to_actual_source_column_metadata(self):
        finding = recorded_result()["findings"][0]
        before = copy.deepcopy(finding)
        rows = self.demo.evidence_rows(finding)
        self.assertEqual(len(rows), 6)
        required = {"sample_id", "batch_id", "time_tick", "time_h", "observed_value", "reference_median",
                    "reference_mad", "reference_spread", "deviation_score", "peer_count", "source_file_id",
                    "source_row_number", "source_column_index", "source_header"}
        self.assertTrue(all(required <= set(row) for row in rows))
        first = rows[0]
        self.assertEqual((first["time_tick"], first["source_row_number"], first["source_column_index"]), (430, 34755, 17))
        self.assertAlmostEqual(first["observed_value"], 298.38)
        self.assertAlmostEqual(first["reference_median"], 297.99)
        self.assertEqual(first["source_header"], "Temperature(T:K)")
        self.assertEqual(finding, before)

    def test_trend_figure_preserves_published_values_units_and_null_gaps(self):
        rows = [{"time_h": 0.2, "value": 298.38}, {"time_h": 0.4, "value": None}, {"time_h": 0.6, "value": 297.99}]
        figure = self.demo.trend_figure(rows, "temperature", "K")
        self.assertEqual(list(figure.data[0].x), [0.2, 0.4, 0.6])
        self.assertEqual(list(figure.data[0].y), [298.38, None, 297.99])
        self.assertFalse(figure.data[0].connectgaps)
        self.assertIn("K", figure.layout.yaxis.title.text)

    def test_reference_envelope_uses_threshold_times_spread_and_gaps_unscoreable_points(self):
        finding = recorded_result()["findings"][0]
        points = []
        for index, (status, median, spread) in enumerate((("scored", 5.0, 1.0),
                ("insufficient_peers", None, None), ("zero_mad_unscorable", 7.0, 0.0), ("scored", 8.0, 2.0))):
            points.append({"time_tick": index + 1, "time_h": (index + 1) / 5, "observed_value": 10.0 + index,
                           "reference_median": median, "reference_spread": spread, "status": status})
        figure = self.demo.finding_figure(finding, points, threshold=6.0, unit_reported="K")
        traces = {trace.name: trace for trace in figure.data}
        self.assertEqual(list(traces["Observed"].y), [10.0, 11.0, 12.0, 13.0])
        self.assertEqual(list(traces["Upper statistical reference"].y), [11.0, None, None, 20.0])
        self.assertEqual(list(traces["Lower statistical reference"].y), [-1.0, None, None, -4.0])
        self.assertFalse(traces["Upper statistical reference"].connectgaps)
        self.assertFalse(traces["Peer median"].connectgaps)
        self.assertTrue(figure.layout.shapes)
        self.assertTrue(any(shape.x0 == 86.0 and shape.x1 == 87.0 for shape in figure.layout.shapes))

    def test_connection_and_result_cache_identity_changes_without_exposing_credentials(self):
        first_values = {"NEO4J_URI": "bolt://127.0.0.1:7687", "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": "secret-one"}
        second_values = {**first_values, "NEO4J_PASSWORD": "secret-two"}
        a = self.demo.connection_fingerprint(first_values)
        b = self.demo.connection_fingerprint(second_values)
        self.assertNotEqual(a, b)
        self.assertEqual(a, self.demo.connection_fingerprint(dict(reversed(list(first_values.items())))))
        self.assertNotIn("secret", a)
        self.assertEqual(len(a), 64)

    def test_effective_config_batch_content_and_connection_each_version_result_cache_key(self):
        from scripts import investigation
        identity = {"content_key": "a" * 64, "dataset_id": "test:synthetic-demo-cache"}
        batch_id = "test:synthetic-demo-cache:batch:001"
        baseline = self.demo.result_cache_key(identity, batch_id, "connection-a")
        self.assertEqual(baseline, self.demo.result_cache_key(dict(identity), batch_id, "connection-a"))
        alternatives = (
            self.demo.result_cache_key({**identity, "content_key": "b" * 64}, batch_id, "connection-a"),
            self.demo.result_cache_key(identity, batch_id + "-other", "connection-a"),
            self.demo.result_cache_key(identity, batch_id, "connection-b"),
            self.demo.result_cache_key(identity, batch_id, "connection-a", investigation.DetectorConfig(threshold=7.0)),
        )
        self.assertTrue(all(value != baseline for value in alternatives))

    def test_changed_current_contract_rejected_despite_prior_healthy_content_identity(self):
        from scripts import graph
        try:
            from .test_graph import ProcessedFixture
        except ImportError:
            from test_graph import ProcessedFixture
        with tempfile.TemporaryDirectory(prefix="pharmagraph-demo-contract-test-") as directory:
            fixture = ProcessedFixture(directory)
            before = {p.name: p.read_bytes() for p in fixture.output.iterdir()}
            with mock.patch.object(graph, "DEFAULT_CONTRACT", fixture.contract_path):
                healthy = self.demo.content_identity(fixture.output)
                self.assertTrue(healthy["content_key"])
            changed_contract = Path(directory) / "changed_contract_copy.json"
            changed_contract.write_bytes(fixture.contract_path.read_bytes() + b"\n")
            with mock.patch.object(graph, "DEFAULT_CONTRACT", changed_contract):
                with self.assertRaises(ValueError):
                    self.demo.content_identity(fixture.output)
            self.assertEqual(before, {p.name: p.read_bytes() for p in fixture.output.iterdir()})


class DemoMockedFailureTests(unittest.TestCase):
    """AppTest errors injected before live I/O; these are not database checks."""

    def test_missing_artifact_is_actionable_without_stack_trace_or_engine_call(self):
        from streamlit.testing.v1 import AppTest
        demo = importlib.import_module("scripts.demo")
        engine = importlib.import_module("scripts.investigation")
        with mock.patch.object(demo, "content_identity", side_effect=FileNotFoundError("Synthetic missing artifact")), \
             mock.patch.object(engine, "investigate_batch", side_effect=AssertionError("Unexpected investigation")):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
            app.session_state["page_navigation"] = "Investigate a batch"
            app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        text = app_text(app).lower()
        self.assertTrue("artifact" in text or "processed" in text)
        self.assertNotIn("traceback", text)
        self.assertNotIn("synthetic missing artifact", text)


if __name__ == "__main__":
    unittest.main()
