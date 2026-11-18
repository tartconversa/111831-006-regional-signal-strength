import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone


@dataclass(frozen=True)
class AnalysisReport:
    """已发布分析的不可变快照。

    除统计结果外，固化发布时的区域映射、来源范围与覆盖缺口，使历史报告
    能回看当时口径，而不受后续来源归属修正或暂停/恢复影响。
    """

    report_id: str
    title: str
    period_start: str
    period_end: str
    source_ids: tuple[str, ...]
    measures: dict[str, float]
    created_at: str
    region_mapping: dict[str, str] = field(default_factory=dict)
    source_scope: dict = field(default_factory=dict)
    regional_results: dict = field(default_factory=dict)
    methodology_notes: tuple[str, ...] = ()
    interpretation_notes: tuple[str, ...] = ()


def create_report(report_id, title, period_start, period_end, source_ids, measures):
    return AnalysisReport(
        report_id=report_id, title=title, period_start=period_start, period_end=period_end,
        source_ids=tuple(sorted(set(source_ids))), measures=dict(measures),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def create_regional_report(report_id, title, breakdown, catalog, *, start=None, end=None):
    """根据区域分析结果与来源目录生成可回看的发布快照。

    快照内的映射与来源范围来自发布时刻的目录；此后目录变化不会改写报告。
    """
    period_start = start if start is not None else breakdown.get("period")
    period_end = end if end is not None else breakdown.get("period")

    sources = catalog.all_sources()
    source_scope = {
        "active_source_ids": tuple(
            source.source_id for source in sources if source.active
        ),
        "suspended_source_ids": tuple(
            source.source_id for source in sources if not source.active
        ),
        "sources": tuple(
            {
                "source_id": source.source_id,
                "region": source.region,
                "language": source.language,
                "active": source.active,
            }
            for source in sources
        ),
    }

    measures = {
        item["region"]: item["value"]
        for item in breakdown["ranking"]
        if item["value"] is not None
    }
    notes = tuple(breakdown.get("methodology_notes", ())) + (
        "报道情绪与计数是媒体层面的观察，不能转述为当地公众态度；"
        "小样本或来源集中的地区排名仅作线索，不代表代表性充分。",
    )

    report = AnalysisReport(
        report_id=report_id,
        title=title,
        period_start=period_start,
        period_end=period_end,
        source_ids=tuple(sorted(
            source["source_id"] for source in source_scope["sources"]
        )),
        measures=measures,
        created_at=datetime.now(timezone.utc).isoformat(),
        region_mapping=catalog.region_mapping(),
        source_scope=source_scope,
        regional_results=breakdown,
        methodology_notes=tuple(breakdown.get("methodology_notes", ())),
        interpretation_notes=notes,
    )
    return replace(report)


def report_to_dict(report):
    return {
        "report_id": report.report_id,
        "title": report.title,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "source_ids": list(report.source_ids),
        "measures": report.measures,
        "created_at": report.created_at,
        "region_mapping": report.region_mapping,
        "source_scope": report.source_scope,
        "regional_results": report.regional_results,
        "methodology_notes": list(report.methodology_notes),
        "interpretation_notes": list(report.interpretation_notes),
    }


def report_to_json(report):
    return json.dumps(report_to_dict(report), ensure_ascii=False, indent=2)


def report_from_dict(payload):
    return AnalysisReport(
        report_id=payload["report_id"],
        title=payload["title"],
        period_start=payload["period_start"],
        period_end=payload["period_end"],
        source_ids=tuple(payload.get("source_ids", ())),
        measures=dict(payload.get("measures", {})),
        created_at=payload["created_at"],
        region_mapping=dict(payload.get("region_mapping", {})),
        source_scope=dict(payload.get("source_scope", {})),
        regional_results=dict(payload.get("regional_results", {})),
        methodology_notes=tuple(payload.get("methodology_notes", ())),
        interpretation_notes=tuple(payload.get("interpretation_notes", ())),
    )


def report_from_json(text):
    return report_from_dict(json.loads(text))
