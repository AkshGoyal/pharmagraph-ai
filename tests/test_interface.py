"""Meaningful offline UI checks: navigation, recorded evidence and assessment states."""
import json
from pathlib import Path
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

from scripts import demo, interface, investigation

ROOT = Path(__file__).resolve().parents[1]


class InterfaceTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)

    def healthy(self, app):
        self.assertFalse(app.exception, [str(e.value) for e in app.exception])
        self.assertFalse(app.error, [str(e.value) for e in app.error])

    def test_overview_and_all_offline_views_never_connect_or_invoke_detector(self):
        with mock.patch.object(demo, "content_identity", side_effect=AssertionError("Unexpected live data access")), \
             mock.patch.object(investigation, "investigate_batch", side_effect=AssertionError("Unexpected detector invocation")):
            app = self.app().run()
            self.healthy(app)
            self.assertEqual(app.radio(key="page_navigation").value, "Project overview")
            self.assertEqual([tab.label for tab in app.tabs], ["The product", "Business & use cases", "Technical architecture"])
            app.button[0].click().run()
            self.healthy(app)
            self.assertEqual(app.radio(key="page_navigation").value, "Recorded walkthrough")
            app.radio(key="page_navigation").set_value("Data & glossary").run()
            self.healthy(app)
            app.text_input(key="glossary_search").set_value("provenance").run()
            self.assertTrue(any("Provenance" in frame.value.to_string() for frame in app.dataframe))
            app.text_input(key="glossary_search").set_value("this-term-does-not-exist").run()
            self.assertTrue(app.info)

    def test_recorded_point_selection_and_export_preserve_exact_evidence(self):
        import streamlit as st
        app = self.app()
        app.session_state["page_navigation"] = "Recorded walkthrough"
        with mock.patch.object(st, "download_button", wraps=st.download_button) as downloads:
            app.run()
            self.healthy(app)
            result = interface.recorded_result("031")
            expected = demo.canonical_json_bytes(result)
            self.assertEqual(downloads.call_args.kwargs["data"], expected)
            evidence = next(frame.value for frame in app.dataframe if "source_row_number" in frame.value.columns)
            self.assertEqual(len(evidence), 6)
            self.assertEqual(float(evidence.iloc[0]["observed_value"]), 298.38)
            self.assertEqual(int(evidence.iloc[0]["source_row_number"]), 34755)
            app.select_slider(key="recorded_point").set_value(5).run()
            self.healthy(app)
            self.assertEqual(downloads.call_args.kwargs["data"], expected)
            self.assertTrue(any("At 87 hours" in heading.value for heading in app.markdown))
            self.assertEqual(json.loads(expected), result)

    def test_assessed_none_and_undocumented_stay_distinct_when_switching_recorded_cases(self):
        app = self.app()
        app.session_state["page_navigation"] = "Recorded walkthrough"
        app.run()
        app.selectbox(key="recorded_batch").set_value("001").run()
        self.healthy(app)
        self.assertTrue(any("not proof" in element.value for element in app.info))
        self.assertFalse(app.select_slider)
        app.selectbox(key="recorded_batch").set_value("091").run()
        self.healthy(app)
        self.assertTrue(any("Not assessed" in element.value for element in app.warning))
        self.assertFalse(app.select_slider)
        app.selectbox(key="recorded_batch").set_value("031").run()
        self.healthy(app)
        self.assertTrue(app.select_slider)


if __name__ == "__main__":
    unittest.main()
