# 区域样本支撑分析

这个 Python 项目整理与“区域样本支撑分析”有关的来源观察，并生成供研究人员复核的统计摘要。

区域分析（`signal_lab.regional_breakdown` / `regional_trends`）在排名与趋势之外，同时输出有效观察数量、来源构成、小样本与来源集中警告及覆盖缺口；地区归属以来源目录（`SourceCatalog`）的现行映射为准，来源的归属修正、暂停与恢复会一致反映到指标与支撑说明上。`create_regional_report` 将发布时刻的区域映射、来源范围与统计结果固化为可回看的快照。口径细节见 `docs/analysis-notes.md`。

## 开发

需要 Python 3.11 或更高版本。安装开发依赖：`python -m pip install -e .`。

运行测试：`python -m unittest discover -s tests -v`。
构建发行包：`python -m build`。
