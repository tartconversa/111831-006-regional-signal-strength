from collections import defaultdict

from .catalog import SourceCatalog

# 有效观察低于该值视为小样本，排名不做代表性暗示。
MIN_OBSERVATIONS = 5
# 单一来源占比达到该阈值视为来源集中。
CONCENTRATION_THRESHOLD = 0.6

METHODOLOGY_NOTES = (
    "数值与占比仅汇总在册且未暂停来源的有效观察；地区归属以来源目录的"
    "现行映射为准，观察记录上的地区字段不参与分组。输出不把媒体报道情绪"
    "或报道计数解释为当地公众态度，也不构成传播效果的因果结论。",
)


def regional_trends(observations, catalog, start, end):
    """对比两个周期的区域指标，趋势与排名同样附样本支撑与覆盖缺口。"""
    start_breakdown = regional_breakdown(observations, catalog, period=start)
    end_breakdown = regional_breakdown(observations, catalog, period=end)

    start_regions = {
        item["region"]: item for item in start_breakdown["ranking"]
    }
    end_regions = {
        item["region"]: item for item in end_breakdown["ranking"]
    }

    regions = []
    for region in sorted(set(start_regions) | set(end_regions)):
        before = start_regions.get(region)
        after = end_regions.get(region)
        start_value = before["value"] if before else None
        end_value = after["value"] if after else None
        if start_value is not None and end_value is not None:
            value_change = end_value - start_value
        else:
            value_change = None
        regions.append({
            "region": region,
            "start_value": start_value,
            "end_value": end_value,
            "value_change": value_change,
            "start_share": before["share_of_total"] if before else None,
            "end_share": after["share_of_total"] if after else None,
            "start_rank": before["rank"] if before else None,
            "end_rank": after["rank"] if after else None,
            "start_observation_count": (
                before["observation_count"] if before else 0
            ),
            "end_observation_count": (
                after["observation_count"] if after else 0
            ),
            "start_source_count": (
                before["source_count"] if before else 0
            ),
            "end_source_count": after["source_count"] if after else 0,
            "start_status": before["status"] if before else "no-data",
            "end_status": after["status"] if after else "no-data",
            "end_warnings": after["warnings"] if after else [],
        })

    return {
        "start_period": _period_label(start),
        "end_period": _period_label(end),
        "regions": regions,
        "start": start_breakdown,
        "end": end_breakdown,
        "methodology_notes": list(METHODOLOGY_NOTES),
    }


def _period_label(period):
    if period is None:
        return None
    return f"{period[0]:04d}-{period[1]:02d}"


def _in_period(observation, period):
    if period is None:
        return True
    return (observation.observed_on.year, observation.observed_on.month) == period


def compare_periods(observations, start, end, *, region=None):
    """汇总两个周期内的观察值与来源覆盖数量。"""
    periods = ((start[0], start[1]), (end[0], end[1]))
    totals = [defaultdict(float), defaultdict(float)]
    sources = [defaultdict(set), defaultdict(set)]
    for observation in observations:
        if region is not None and observation.region != region:
            continue
        key = (observation.observed_on.year, observation.observed_on.month)
        if key not in periods:
            continue
        slot = periods.index(key)
        totals[slot][observation.topic] += observation.value
        sources[slot][observation.topic].add(observation.source_id)
    topics = sorted(set(totals[0]) | set(totals[1]))
    return {topic: {
        "start_value": totals[0][topic], "end_value": totals[1][topic],
        "start_sources": len(sources[0][topic]), "end_sources": len(sources[1][topic]),
    } for topic in topics}


def regional_breakdown(observations, catalog, *, period=None):
    """按来源目录的现行地区映射汇总观察，并附样本支撑与覆盖缺口。

    指标只统计“在册且未暂停来源”的观察；缺失观察的在册地区以
    no-data 形态保留，不压成零值。返回结构同时给出排序、支撑等级、
    来源构成与覆盖缺口，调用方据此判断差异是否值得跟进。
    """
    if not isinstance(catalog, SourceCatalog):
        raise TypeError("catalog must be a SourceCatalog")

    effective = []
    unattributed = []
    suspended = []
    stale_region = []

    for observation in observations:
        if not _in_period(observation, period):
            continue
        source = catalog.get(observation.source_id)
        if source is None:
            unattributed.append(observation)
        elif not source.active:
            suspended.append((observation, source))
        else:
            if observation.region != source.region:
                stale_region.append((observation, source))
            effective.append((observation, source))

    region_value = defaultdict(float)
    region_observation_ids = defaultdict(list)
    region_source_ids = defaultdict(set)
    source_value = defaultdict(float)
    source_observation_count = defaultdict(int)
    source_total = defaultdict(float)

    for observation, source in effective:
        region = source.region
        region_value[region] += observation.value
        region_observation_ids[region].append(observation.observation_id)
        region_source_ids[region].add(source.source_id)
        source_value[(region, source.source_id)] += observation.value
        source_observation_count[(region, source.source_id)] += 1
        source_total[region] += observation.value

    total_value = sum(region_value.values())
    total_observations = sum(len(ids) for ids in region_observation_ids.values())
    total_sources = set()
    for ids in region_source_ids.values():
        total_sources.update(ids)

    regions = []
    for region in catalog.regions(active_only=True):
        observation_ids = sorted(region_observation_ids.get(region, ()))
        observed = bool(observation_ids)
        expected_sources = sorted(
            source.source_id for source in catalog.active_sources(region)
        )
        observed_source_ids = region_source_ids.get(region, set())
        missing_sources = sorted(set(expected_sources) - observed_source_ids)

        value = region_value.get(region, 0.0)
        share = (value / total_value) if observed and total_value else None
        composition = []
        for source_id in sorted(observed_source_ids):
            source_share = (
                source_value[(region, source_id)] / source_total[region]
                if source_total[region]
                else None
            )
            composition.append({
                "source_id": source_id,
                "observation_count": source_observation_count[(region, source_id)],
                "value": source_value[(region, source_id)],
                "share_of_region": source_share,
            })

        warnings = []
        if not observed:
            status = "no-data"
        else:
            count = len(observation_ids)
            small_sample = count < MIN_OBSERVATIONS
            if small_sample:
                status = "thin"
                warnings.append({
                    "code": "small-sample",
                    "detail": (
                        f"仅 {count} 条有效观察（阈值 {MIN_OBSERVATIONS}），"
                        "排名波动可能由单条观察驱动。"
                    ),
                })
            else:
                status = "supported"
            dominant = max(
                composition,
                key=lambda item: item["share_of_region"] or 0.0,
                default=None,
            )
            if dominant is not None and (
                dominant["share_of_region"] or 0.0
            ) >= CONCENTRATION_THRESHOLD:
                # 小样本优先标记为 thin；来源集中仍作为警告保留。
                if not small_sample:
                    status = "concentrated"
                warnings.append({
                    "code": "dominant-source",
                    "detail": (
                        f"来源 {dominant['source_id']} 占该地区 "
                        f"{dominant['share_of_region']:.0%} 的观察值，"
                        "不代表来源覆盖已经充分。"
                    ),
                })
            if missing_sources:
                warnings.append({
                    "code": "coverage-gap",
                    "detail": (
                        "在册有效来源中以下来源本周期无观察："
                        + ", ".join(missing_sources)
                    ),
                })

        regions.append({
            "region": region,
            "status": status,
            "observation_count": len(observation_ids),
            "observation_ids": observation_ids,
            "source_count": len(observed_source_ids),
            "active_source_count": len(expected_sources),
            "source_ids": sorted(observed_source_ids),
            "source_composition": composition,
            "value": value if observed else None,
            "share_of_total": share,
            "missing_source_ids": missing_sources,
            "warnings": warnings,
            "rank": None,
        })

    observed_regions = [item for item in regions if item["status"] != "no-data"]
    observed_regions.sort(key=lambda item: (-item["value"], item["region"]))
    no_data_regions = [item for item in regions if item["status"] == "no-data"]
    no_data_regions.sort(key=lambda item: item["region"])
    ordered = observed_regions + no_data_regions
    for index, item in enumerate(observed_regions, start=1):
        item["rank"] = index

    coverage_gaps = {
        "regions_without_observations": [
            {
                "region": item["region"],
                "active_source_count": item["active_source_count"],
                "active_source_ids": sorted(
                    source.source_id
                    for source in catalog.active_sources(item["region"])
                ),
            }
            for item in no_data_regions
        ],
        "unattributed_observation_ids": sorted(
            observation.observation_id for observation in unattributed
        ),
        "suspended_sources": sorted({
            source.source_id for _, source in suspended
        }),
        "suspended_observation_ids": sorted(
            observation.observation_id for observation, _ in suspended
        ),
        "stale_region_observations": sorted(
            (observation.observation_id, source.region)
            for observation, source in stale_region
        ),
    }

    return {
        "period": _period_label(period),
        "ranking": ordered,
        "totals": {
            "effective_observation_count": total_observations,
            "active_region_count": len(regions),
            "observed_region_count": len(observed_regions),
            "active_source_count": len(total_sources),
            "total_value": total_value,
        },
        "coverage_gaps": coverage_gaps,
        "thresholds": {
            "min_observations": MIN_OBSERVATIONS,
            "concentration_threshold": CONCENTRATION_THRESHOLD,
        },
        "methodology_notes": list(METHODOLOGY_NOTES),
    }
