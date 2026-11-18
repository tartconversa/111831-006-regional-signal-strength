from dataclasses import dataclass, replace

from .records import Source


class SourceCatalog:
    """来源目录，维护来源与地区之间的现行映射。

    来源归属修正、暂停与恢复都通过本类完成；分析始终以目录中的现行
    映射为准，保证相关地区的指标随目录变更一致更新。
    """

    def __init__(self, sources=()):
        self._sources = {source.source_id: source for source in sources}

    def get(self, source_id):
        return self._sources.get(source_id)

    def active_sources(self, region=None):
        values = (source for source in self._sources.values() if source.active)
        if region is not None:
            values = (source for source in values if source.region == region)
        return tuple(sorted(values, key=lambda source: source.source_id))

    def all_sources(self):
        return tuple(sorted(self._sources.values(), key=lambda source: source.source_id))

    def upsert(self, source):
        """登记或修正来源（含归属地区修正），返回更新后的目录条目。"""
        self._sources[source.source_id] = source
        return source

    def suspend(self, source_id):
        source = self._require(source_id)
        suspended = replace(source, active=False)
        self._sources[source_id] = suspended
        return suspended

    def resume(self, source_id):
        source = self._require(source_id)
        resumed = replace(source, active=True)
        self._sources[source_id] = resumed
        return resumed

    def regions(self, active_only=False):
        sources = self.active_sources() if active_only else self.all_sources()
        return tuple(sorted({source.region for source in sources}))

    def region_mapping(self):
        """现行来源 -> 地区映射，供发布快照使用。"""
        return {source_id: source.region for source_id, source in sorted(self._sources.items())}

    def _require(self, source_id):
        try:
            return self._sources[source_id]
        except KeyError:
            raise KeyError(f"unknown source: {source_id}") from None
