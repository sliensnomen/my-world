"""WGP-econ 扩展包 v0.1 —— 数值系统审计（CA6xx）。

由 canonlint --pack econ 启用。core 不依赖本模块。
"""
from __future__ import annotations

PACK_NAME = "econ"
PACK_VERSION = "0.1"

# 启用本包时注入 core 的合法字段集
KNOWN_FIELDS = {"figures"}

# 参数表 v0（PROTOCOL-ECON.md §4；每条注明出处）
PARAM_TABLE = [
    {"id": "standing-army-ratio", "subject": "military_size", "base": "population",
     "max_ratio": 0.02,
     "source": "前现代常备军供养上限启发式（中世纪欧洲估算 1–2%）"},
    {"id": "wartime-garrison-ratio", "subject": "garrison", "base": "population",
     "max_ratio": 0.10,
     "source": "围城战总动员极限启发式"},
]


def check_entry(meta: dict, rel: str, add) -> None:
    """meta: 条目 frontmatter；rel: 条目定位；add(rule, level, msg) 收集发现。"""
    figs = meta.get("figures")
    if figs is None:
        return
    if not isinstance(figs, dict):
        add("CA601", "error", "figures 必须是映射 {名称: {value, unit}}")
        return

    parsed: dict[str, float] = {}
    for name, f in figs.items():
        if not isinstance(f, dict):
            add("CA601", "error", f"figures.{name} 必须是对象 {{value, unit}}")
            continue
        v, u = f.get("value"), f.get("unit")
        if u is None:
            add("CA601", "error", f"figures.{name} 缺 unit")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            add("CA601", "error", f"figures.{name}.value={v!r} 非数字")
            continue
        parsed[name] = float(v)

    # CA602：参数表硬边界。缺数据不报错——subject/base 缺一即跳过。
    for rule in PARAM_TABLE:
        s, b = rule["subject"], rule["base"]
        if s not in parsed or b not in parsed:
            continue
        if parsed[b] == 0:
            continue
        ratio = parsed[s] / parsed[b]
        if ratio > rule["max_ratio"]:
            just = figs.get(s, {}).get("justification") if isinstance(figs.get(s), dict) else None
            if not just:
                add("CA602", "warning",
                    f"{s}={parsed[s]:g} / {b}={parsed[b]:g} = {ratio:.1%}，"
                    f"越参数表 {rule['id']} 上界 {rule['max_ratio']:.0%}"
                    f"（{rule['source']}），且无 justification")
