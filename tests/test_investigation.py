"""Independent synthetic method tests; no manufacturing accuracy is asserted."""
import copy
from dataclasses import FrozenInstanceError
import importlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from .test_graph import ProcessedFixture, canonical_hash, sha256
except ImportError:
    from test_graph import ProcessedFixture, canonical_hash, sha256


def measurement(batch_id, tick, value):
    return {"batch_id": batch_id, "sample_id": f"{batch_id}:tick:{tick:06d}",
            "time_tick": tick, "time_h": tick / 5, "value": value,
            "source_file_id": "test:synthetic-method:timeseries", "source_row_number": tick + 1}


def symmetric_peers(ticks=range(1, 9)):
    return {f"synthetic-peer-{index}": [measurement(f"synthetic-peer-{index}", t, value) for t in ticks]
            for index, value in enumerate((-2.0, -1.0, 0.0, 1.0, 2.0))}


def result_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


class InvestigationFixture(ProcessedFixture):
    """Eight synthetic batches: six compatible, one other regime, one unknown.

    Target 1 has eight injected aeration deviations. Peers 2..6 are symmetric
    constants (-2,-1,0,1,2), giving median0 and MAD1. All other selected target
    variables equal the reference median. Nothing is ingested from an archive.
    """

    def __init__(self, directory):
        super().__init__(directory)
        batch_template = copy.deepcopy(self.rows["batches"][0])
        sample_template = copy.deepcopy(self.rows["samples"][1])
        refs = (1, 2, 3, 4, 5, 6, 31, 91)
        self.rows["batches"] = []
        self.rows["samples"] = []
        for index, ref in enumerate(refs):
            batch_id = f"{self.dataset_id}:batch:{ref:03d}"
            regime = "recipe_driven" if ref <= 6 else "operator_controlled" if ref == 31 else "not_documented"
            batch = {**batch_template, "batch_id": batch_id, "batch_ref": ref, "source_row_number": index + 1,
                     "fault_present": ref == 91, "control_regime": regime, "sample_count": 8,
                     "time_end_h": 1.6, "timeseries_first_source_row": index * 8 + 1,
                     "timeseries_last_source_row": index * 8 + 8}
            self.rows["batches"].append(batch)
            for tick in range(1, 9):
                value = float(ref - 4) if 2 <= ref <= 6 else 0.0
                sample = {**sample_template, "batch_id": batch_id, "batch_ref": ref,
                          "sample_id": batch_id + f":tick:{tick:06d}", "source_row_number": index * 8 + tick,
                          "time_tick": tick, "time_h": tick / 5, "metadata_34_raw": ref,
                          "batch_fault_flag_raw": int(ref == 91), "fault_reference_raw": 0}
                for variable in ("aeration_rate", "sugar_feed_rate", "ph", "temperature"):
                    sample[variable] = 10.0 if ref == 1 and variable == "aeration_rate" else value
                self.rows["samples"].append(sample)
        self.contract["source"]["expected_batch_refs"] = list(refs)
        for member, count in zip(self.contract["source"]["members"], (8, 64)):
            member["expected_rows"] = count
        self.contract_path.write_text(json.dumps(self.contract, indent=2) + "\n")
        self.manifest["cache_inputs"]["contract_sha256"] = sha256(self.contract_path)
        self.manifest["cache_key"] = canonical_hash(self.manifest["cache_inputs"])
        for member, count in zip(self.manifest["source"]["members"], (8, 64)):
            member["rows"] = count
        for name in self.rows:
            self.write_table(name)


class InvestigationMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = importlib.import_module("scripts.investigation")

    def config(self, **kwargs):
        return self.engine.DetectorConfig(**{"min_peers": 3, "min_consecutive": 2, **kwargs})

    def score(self, target_values, *, ticks=None, peers=None, config=None):
        ticks = list(ticks) if ticks is not None else list(range(1, len(target_values) + 1))
        target = [measurement("synthetic-target", tick, value) for tick, value in zip(ticks, target_values)]
        return self.engine.score_variable(target, symmetric_peers() if peers is None else peers,
                                           self.config() if config is None else config)

    def test_default_configuration_and_frozen_strict_allowlist(self):
        config = self.engine.DetectorConfig()
        self.assertEqual(config.variables, ("aeration_rate", "sugar_feed_rate", "ph", "temperature"))
        self.assertEqual((config.min_peers, config.threshold, config.min_consecutive), (10, 6.0, 5))
        with self.assertRaises(FrozenInstanceError):
            config.threshold = 1
        invalid = ({"min_peers": True}, {"min_peers": 1}, {"min_peers": 2.1},
                   {"threshold": 0}, {"threshold": float("nan")}, {"threshold": float("inf")},
                   {"threshold": True}, {"min_consecutive": 0}, {"min_consecutive": True},
                   {"variables": ()}, {"variables": ("aeration_rate", "aeration_rate")},
                   {"variables": ("fault_reference_raw",)}, {"variables": ("paa_offline",)},
                   {"variables": ["ph"]}, {"peer_batch_ids": ("x", "x")}, {"peer_batch_ids": ("",)})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                self.engine.DetectorConfig(**kwargs)

    def test_independent_median_mad_score_support_and_interval_evidence(self):
        result = self.score([10.0, 12.0, 14.0])
        scores = [value / 1.4826 for value in (10.0, 12.0, 14.0)]
        for point, score in zip(result["points"], scores):
            self.assertEqual((point["reference_median"], point["reference_mad"], point["reference_spread"]),
                             (0.0, 1.0, 1.4826))
            self.assertAlmostEqual(point["deviation_score"], score)
            self.assertEqual(point["peer_count"], 5)
            self.assertEqual(point["peer_batch_ids"], sorted(symmetric_peers()))
            self.assertEqual(len(point["peer_measurements"]), 5)
            self.assertTrue(point["exceeds"])
            for peer in point["peer_measurements"]:
                self.assertEqual(set(peer), {"batch_id", "sample_id", "time_tick", "time_h", "value",
                                            "source_file_id", "source_row_number"})
        self.assertEqual(len(result["intervals"]), 1)
        interval = result["intervals"][0]
        self.assertEqual((interval["start_tick"], interval["end_tick"], interval["point_count"]), (1, 3, 3))
        self.assertEqual((interval["start_time_h"], interval["end_time_h"], interval["direction"]), (0.2, 0.6, "above"))
        self.assertAlmostEqual(interval["statistical_deviation_score"], sum(scores) / 3)
        self.assertAlmostEqual(interval["peak_deviation_score"], max(scores))
        self.assertEqual(interval["evidence"], result["points"])

    def test_strict_threshold_does_not_count_equal_score(self):
        boundary = 10.0 / 1.4826
        result = self.score([10.0, 10.0 + 1e-8], config=self.config(threshold=boundary, min_consecutive=1))
        self.assertFalse(result["points"][0]["exceeds"])
        self.assertTrue(result["points"][1]["exceeds"])
        self.assertEqual([(r["start_tick"], r["end_tick"]) for r in result["intervals"]], [(2, 2)])

    def test_even_peer_count_uses_midpoint_median_and_raw_mad(self):
        peers = {str(i): [measurement(str(i), 1, value)] for i, value in enumerate((-10, 1, 4, 9))}
        point = self.score([20], peers=peers, config=self.config(threshold=2, min_consecutive=1))["points"][0]
        self.assertEqual(point["reference_median"], 2.5)
        self.assertEqual(point["reference_mad"], 4.0)
        self.assertAlmostEqual(point["reference_spread"], 5.9304)
        self.assertAlmostEqual(point["deviation_score"], 17.5 / 5.9304)

    def test_direction_changes_nonexceedances_and_gaps_split_runs(self):
        result = self.score([10, 10, 10, -10, -10, 0, 10, 10])
        runs = sorted((r["start_tick"], r["end_tick"], r["direction"]) for r in result["intervals"])
        self.assertEqual(runs, [(1, 3, "above"), (4, 5, "below"), (7, 8, "above")])
        gap = self.score([10, 10, 10, 10], ticks=[1, 2, 4, 5])
        self.assertEqual(sorted((r["start_tick"], r["end_tick"]) for r in gap["intervals"]), [(1, 2), (4, 5)])

    def test_minimum_consecutive_counts_observations_and_five_span_point_eight_hours(self):
        short = self.score([10] * 4, config=self.config(min_consecutive=5))
        self.assertEqual(short["intervals"], [])
        retained = self.score([10] * 5, config=self.config(min_consecutive=5))["intervals"][0]
        self.assertEqual(retained["point_count"], 5)
        self.assertAlmostEqual(retained["end_time_h"] - retained["start_time_h"], 0.8)

    def test_zero_mad_equal_and_unscorable_never_invent_epsilon_or_infinity(self):
        peers = {key: [measurement(key, t, 4.0) for t in (1, 2)] for key in ("a", "b", "c")}
        result = self.score([4.0, 10.0], peers=peers)
        equal, different = result["points"]
        self.assertEqual((equal["status"], equal["deviation_score"], equal["exceeds"]), ("zero_mad_equal", 0, False))
        self.assertEqual(different["status"], "zero_mad_unscorable")
        self.assertIsNone(different["deviation_score"])
        self.assertFalse(different["exceeds"])
        self.assertEqual(result["intervals"], [])
        result_bytes(result)

    def test_missing_and_nonfinite_target_values_break_runs_and_stay_json_safe(self):
        for missing in (None, float("nan"), float("inf"), -float("inf")):
            result = self.score([10, 10, missing, 10, 10])
            self.assertEqual(sorted((r["start_tick"], r["end_tick"]) for r in result["intervals"]), [(1, 2), (4, 5)])
            self.assertIsNone(result["points"][2]["deviation_score"])
            self.assertFalse(result["points"][2]["exceeds"])
            result_bytes(result)

    def test_coverage_omits_nonfinite_peers_and_distinguishes_unmatched_ticks(self):
        peers = symmetric_peers(ticks=(1, 2))
        peers["synthetic-peer-0"][0]["value"] = None
        peers["synthetic-peer-1"][0]["value"] = float("nan")
        peers["synthetic-peer-2"][0]["value"] = float("inf")
        result = self.score([10, 10, 10], peers=peers)
        self.assertEqual((result["points"][0]["peer_count"], result["points"][0]["status"]), (2, "insufficient_peers"))
        self.assertEqual(result["points"][1]["peer_count"], 5)
        self.assertEqual((result["points"][2]["peer_count"], result["points"][2]["status"]), (0, "unmatched_tick"))
        self.assertEqual(result["skipped_tick_counts"]["insufficient_peers"], 1)
        self.assertEqual(result["skipped_tick_counts"]["unmatched_tick"], 1)
        result_bytes(result)

    def test_target_always_excluded_and_input_order_is_deterministic(self):
        target = [measurement("synthetic-target", tick, 10) for tick in (3, 1, 2)]
        peers = symmetric_peers()
        peers["synthetic-target"] = copy.deepcopy(target)
        result = self.engine.score_variable(target, peers, self.config())
        self.assertTrue(all(p["peer_count"] == 5 and "synthetic-target" not in p["peer_batch_ids"] for p in result["points"]))
        reordered = {key: list(reversed(value)) for key, value in reversed(list(peers.items()))}
        repeat = self.engine.score_variable(list(reversed(target)), reordered, self.config())
        self.assertEqual(result_bytes(result), result_bytes(repeat))

    def test_duplicate_ticks_and_invalid_coordinate_types_are_rejected(self):
        valid = measurement("synthetic-target", 1, 10)
        with self.assertRaises(ValueError):
            self.engine.score_variable([valid, dict(valid)], symmetric_peers(), self.config())
        for key, value in (("time_tick", True), ("time_tick", 1.0), ("time_tick", -1),
                           ("time_h", "0.2"), ("time_h", float("nan")),
                           ("source_row_number", True), ("source_row_number", 0)):
            record = {**valid, key: value}
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, TypeError)):
                self.engine.score_variable([record], symmetric_peers(), self.config())
        peers = symmetric_peers()
        peers["synthetic-peer-0"].append(dict(peers["synthetic-peer-0"][0]))
        with self.assertRaises(ValueError):
            self.engine.score_variable([valid], peers, self.config())


if __name__ == "__main__":
    unittest.main()
