import unittest
from datetime import date

from signal_lab.analysis import regional_breakdown, regional_trends
from signal_lab.catalog import SourceCatalog
from signal_lab.records import Observation, Source
from signal_lab.report import create_regional_report, report_from_json, report_to_json


def build_catalog():
    return SourceCatalog([
        Source("desk-ea-1", "east-asia", "zh"),
        Source("desk-ea-2", "east-asia", "ko"),
        Source("desk-eu-1", "europe", "en"),
        Source("desk-latam-1", "latin-america", "es"),
        Source("desk-paused", "europe", "fr", active=False),
    ])


def build_observations():
    # east-asia: 6 条、来源分散；europe: 1 条（小样本）；
    # latin-america: 无观察（缺口，不能压成零）。
    rows = []
    for index, value in enumerate((3, 4, 2, 5, 3, 4), start=1):
        source_id = "desk-ea-1" if index <= 5 else "desk-ea-2"
        rows.append(Observation(
            f"ea-{index}", source_id, date(2026, 11, index),
            "international-cooperation", value,
            region="east-asia",
        ))
    rows.append(Observation(
        "eu-1", "desk-eu-1", date(2026, 11, 2),
        "international-cooperation", 7, region="europe",
    ))
    rows.append(Observation(
        "paused-1", "desk-paused", date(2026, 11, 3),
        "international-cooperation", 9, region="europe",
    ))
    rows.append(Observation(
        "unknown-1", "desk-offboarded", date(2026, 11, 4),
        "international-cooperation", 1, region="global",
    ))
    return rows


class RegionBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.catalog = build_catalog()
        self.breakdown = regional_breakdown(
            build_observations(), self.catalog, period=(2026, 11)
        )

    def test_ranking_carries_sample_support_and_source_composition(self):
        ranking = self.breakdown["ranking"]
        east_asia = next(item for item in ranking if item["region"] == "east-asia")
        self.assertEqual(east_asia["rank"], 1)
        self.assertEqual(east_asia["observation_count"], 6)
        self.assertEqual(east_asia["source_count"], 2)
        self.assertEqual(
            {entry["source_id"] for entry in east_asia["source_composition"]},
            {"desk-ea-1", "desk-ea-2"},
        )
        dominant = east_asia["source_composition"][0]
        self.assertAlmostEqual(dominant["share_of_region"], 17 / 21)
        self.assertLess(east_asia["share_of_total"], 1.0)

    def test_small_sample_region_is_flagged_instead_of_promoted(self):
        europe = next(
            item for item in self.breakdown["ranking"] if item["region"] == "europe"
        )
        # 单条观察的均值更高，但排名仍在大样本地区之后（按总值）。
        self.assertEqual(europe["rank"], 2)
        self.assertEqual(europe["status"], "thin")
        self.assertIn("small-sample", {w["code"] for w in europe["warnings"]})

    def test_missing_region_is_retained_as_no_data_not_zero(self):
        latam = next(
            item for item in self.breakdown["ranking"]
            if item["region"] == "latin-america"
        )
        self.assertEqual(latam["status"], "no-data")
        self.assertIsNone(latam["value"])
        self.assertIsNone(latam["share_of_total"])
        self.assertIsNone(latam["rank"])
        self.assertEqual(latam["observation_count"], 0)
        gaps = self.breakdown["coverage_gaps"]["regions_without_observations"]
        self.assertEqual(
            [gap["region"] for gap in gaps], ["latin-america"]
        )

    def test_suspended_and_unattributed_observations_are_excluded_but_listed(self):
        europe = next(
            item for item in self.breakdown["ranking"] if item["region"] == "europe"
        )
        self.assertEqual(europe["observation_count"], 1)
        self.assertEqual(europe["value"], 7.0)
        gaps = self.breakdown["coverage_gaps"]
        self.assertEqual(gaps["suspended_sources"], ["desk-paused"])
        self.assertEqual(gaps["suspended_observation_ids"], ["paused-1"])
        self.assertEqual(
            gaps["unattributed_observation_ids"], ["unknown-1"]
        )
        self.assertEqual(
            self.breakdown["totals"]["effective_observation_count"], 7
        )

    def test_dominant_source_warns_against_representativeness(self):

        catalog = SourceCatalog([Source("only", "mideast", "ar")])
        rows = [
            Observation(f"m-{i}", "only", date(2026, 11, i + 1), "t", i + 1)
            for i in range(6)
        ]
        breakdown = regional_breakdown(rows, catalog, period=(2026, 11))
        mideast = breakdown["ranking"][0]
        self.assertEqual(mideast["status"], "concentrated")
        self.assertIn(
            "dominant-source", {w["code"] for w in mideast["warnings"]}
        )

    def test_stale_region_on_observation_is_ignored_for_grouping(self):

        catalog = SourceCatalog([Source("desk", "europe", "en")])
        rows = [
            Observation("o-1", "desk", date(2026, 11, 1), "t", 2, region="asia"),
        ]
        breakdown = regional_breakdown(rows, catalog, period=(2026, 11))
        self.assertEqual(
            [item["region"] for item in breakdown["ranking"]], ["europe"]
        )
        self.assertEqual(
            breakdown["coverage_gaps"]["stale_region_observations"],
            [("o-1", "europe")],
        )

    def test_methodology_notes_warn_against_attitude_interpretation(self):
        notes = " ".join(self.breakdown["methodology_notes"])
        self.assertIn("公众态度", notes)
        self.assertIn("现行映射", notes)


class CatalogConsistencyTests(unittest.TestCase):
    def test_attribution_correction_moves_metrics_between_regions(self):

        catalog = build_catalog()
        rows = build_observations()
        before = regional_breakdown(rows, catalog, period=(2026, 11))
        east_before = next(
            item for item in before["ranking"] if item["region"] == "east-asia"
        )
        self.assertEqual(east_before["observation_count"], 6)

        # 归属修正：desk-ea-2 划入 latin-america。
        catalog.upsert(Source("desk-ea-2", "latin-america", "ko"))
        after = regional_breakdown(rows, catalog, period=(2026, 11))
        regions = {item["region"]: item for item in after["ranking"]}
        self.assertEqual(regions["east-asia"]["observation_count"], 5)
        self.assertEqual(regions["east-asia"]["source_count"], 1)
        self.assertEqual(regions["latin-america"]["observation_count"], 1)
        self.assertEqual(regions["latin-america"]["source_ids"], ["desk-ea-2"])
        # 支撑说明同步更新，不再把 latin-america 列为无观察缺口。
        self.assertEqual(
            after["coverage_gaps"]["regions_without_observations"], []
        )

    def test_suspend_and_resume_keep_indicators_consistent(self):

        catalog = build_catalog()
        rows = build_observations()

        catalog.resume("desk-paused")
        resumed = regional_breakdown(rows, catalog, period=(2026, 11))
        europe = next(
            item for item in resumed["ranking"] if item["region"] == "europe"
        )
        self.assertEqual(europe["observation_count"], 2)
        self.assertEqual(europe["source_count"], 2)
        self.assertEqual(
            resumed["coverage_gaps"]["suspended_sources"], []
        )

        catalog.suspend("desk-eu-1")
        suspended = regional_breakdown(rows, catalog, period=(2026, 11))
        regions = {item["region"]: item for item in suspended["ranking"]}
        self.assertEqual(regions["europe"]["observation_count"], 1)
        self.assertEqual(
            regions["europe"]["source_ids"], ["desk-paused"]
        )
        self.assertIn(
            "desk-eu-1", suspended["coverage_gaps"]["suspended_sources"]
        )

    def test_unknown_source_operations_raise(self):
        catalog = build_catalog()
        with self.assertRaises(KeyError):
            catalog.suspend("desk-ghost")
        with self.assertRaises(KeyError):
            catalog.resume("desk-ghost")


class RegionalTrendTests(unittest.TestCase):
    def test_trend_compares_periods_with_support_evidence(self):

        catalog = SourceCatalog([Source("desk", "europe", "en")])
        rows = [
            Observation("o-1", "desk", date(2026, 10, 1), "t", 2),
            Observation("o-2", "desk", date(2026, 11, 1), "t", 5),
            Observation("o-3", "desk", date(2026, 11, 2), "t", 3),
        ]
        result = regional_trends(rows, catalog, (2026, 10), (2026, 11))
        europe = result["regions"][0]
        self.assertEqual(europe["start_value"], 2.0)
        self.assertEqual(europe["end_value"], 8.0)
        self.assertEqual(europe["value_change"], 6.0)
        self.assertEqual(europe["start_observation_count"], 1)
        self.assertEqual(europe["end_observation_count"], 2)
        self.assertEqual(europe["end_status"], "thin")
        self.assertEqual(result["start"]["period"], "2026-10")


class ReportSnapshotTests(unittest.TestCase):
    def test_published_report_keeps_historical_mapping_and_scope(self):

        catalog = build_catalog()
        rows = build_observations()
        breakdown = regional_breakdown(rows, catalog, period=(2026, 11))
        report = create_regional_report(
            "rpt-1", "区域月报", breakdown, catalog
        )

        self.assertEqual(report.region_mapping["desk-ea-1"], "east-asia")
        self.assertIn(
            "desk-paused", report.source_scope["suspended_source_ids"]
        )
        self.assertEqual(
            report.regional_results["coverage_gaps"]["suspended_sources"],
            ["desk-paused"],
        )
        self.assertTrue(report.interpretation_notes)

        # 发布后再修正归属与暂停状态，快照不变。
        catalog.upsert(Source("desk-ea-1", "oceania", "zh"))
        catalog.suspend("desk-eu-1")
        restored = report_from_json(report_to_json(report))
        self.assertEqual(
            restored.region_mapping["desk-ea-1"], "east-asia"
        )
        self.assertEqual(
            restored.regional_results["ranking"][0]["region"], "east-asia"
        )
        self.assertEqual(restored.report_id, "rpt-1")
        self.assertEqual(restored.period_start, "2026-11")


if __name__ == "__main__":
    unittest.main()
