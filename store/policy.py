"""判定口径（#14）：存储层不替引擎做理论决定。

存储层的 `Entry` 只负责「原始字节 → 契约视图」；判定层需要的口径差异
（depends_on 注解严格度、近失关系名是否真的改名建边）在这里显式声明，
由引擎在启动时把 `JudgmentPolicy` 装进自己的 `Entry` 类。

以前这两项散落在 store/model.py 的类默认值与注释里，存储层事实上保存着
「引擎政策」；现在它们是具名常量：新增引擎 = 新增一个 `JudgmentPolicy`，
而不是再改 store。默认值与原行为逐字节一致（快照不变），只是把决定搬到了明处。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JudgmentPolicy:
    """一个引擎的判定口径。"""

    engine: str
    #: depends_on 对象的 kind / critical 是否必填（协议 §5.4 的严格度）。
    depends_on_requires_annotations: bool
    #: 契约登记的历史拼法之外，编辑距离 ≤1 的近失是否真的改名建边（CA110 守卫）。
    rename_near_miss_edges: bool


#: canonlint（WGP 治理层）的口径：注解必填、近失换名建边。
CANONLINT_POLICY = JudgmentPolicy(
    engine="canonlint",
    depends_on_requires_annotations=True,
    rename_near_miss_edges=True,
)

#: classlint（生产关系层）的口径：注解可选、近失换名建边（协议 §2.2）。
CLASSLINT_POLICY = JudgmentPolicy(
    engine="classlint",
    depends_on_requires_annotations=False,
    rename_near_miss_edges=True,
)
