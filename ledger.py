"""事件流水（协议 1.2）——事件字段解析与派生状态。

卡片是账户，事件是流水，现在的状态是算出来的（docs/事件流水设计.md）。
本模块只提供判定原料：事件长什么样、流水按什么顺序、每个客体最后在谁手里。
判语（什么算错）在 canonlint.py 的 CA7xx；本模块不出现任何规则编号。
"""
from __future__ import annotations

EVENT_KINDS = {"transfer", "custody", "move", "create", "destroy",
               "grant", "birth", "death"}
