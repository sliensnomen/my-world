"""WGP-econ 扩展包 v0.3 —— 数值系统审计（CA6xx）。

由 canonlint --pack econ 启用。core 不依赖本模块。
"""
from __future__ import annotations

import math
from pathlib import Path

import yaml

PACK_NAME = "econ"
PACK_VERSION = "0.3"

# 启用本包时注入 core 的合法字段集
KNOWN_FIELDS = {"figures"}

ECON_CONFIG = "econ.yaml"
FOOD_PARAM = "food_per_person_day"

# 参数表 v0（PROTOCOL-ECON.md §4；每条注明出处）
PARAM_TABLE = [
    {"id": "standing-army-ratio", "subject": "military_size", "base": "population",
     "max_ratio": 0.02,
     "source": "前现代常备军供养上限启发式（中世纪欧洲估算 1–2%）"},
    {"id": "wartime-garrison-ratio", "subject": "garrison", "base": "population",
     "max_ratio": 0.10,
     "source": "围城战总动员极限启发式"},
]


def _finite_number(value) -> float | None:
    """把 YAML 数值转成有限 float；bool、超大整数与 nan/inf 都返回 None。"""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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
        elif not isinstance(u, str) or not u.strip():
            # 规格 PROTOCOL-ECON.md:25「unit 必须是字符串，自由文本单位」。类型不查的话
            # `unit: 123` / `true` / `[a]` / `{}` / 空串 全都静默通过，而 CA602 照样拿它
            # 参与参数表比较——一个不是单位的单位，在结论里被当成合法的单位。
            add("CA601", "error",
                f"figures.{name}.unit={u!r} 必须是非空字符串（自由文本单位，如 `石/亩`）")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            add("CA601", "error", f"figures.{name}.value={v!r} 非数字")
            continue
        value = _finite_number(v)
        if value is None:
            add("CA601", "error",
                f"figures.{name}.value={v!r} 不是有限数字（nan/inf/超出范围不能当世界数）")
            continue
        if value < 0:
            add("CA601", "error", f"figures.{name}.value={v!r} 不能为负（数量没有负值）")
            continue
        parsed[name] = value

    # CA602：参数表硬边界。缺数据不报错——subject/base 缺一即跳过。
    for rule in PARAM_TABLE:
        s, b = rule["subject"], rule["base"]
        if s not in parsed or b not in parsed:
            continue
        if parsed[b] == 0:
            if parsed[s] > 0:
                add("CA602", "warning",
                    f"{b}=0 但 {s}={parsed[s]:g}——零分母无法评估参数表；"
                    f"零人口不可能供养军队，请检查 figures")
            continue
        ratio = parsed[s] / parsed[b]
        if ratio > rule["max_ratio"]:
            just = figs.get(s, {}).get("justification") if isinstance(figs.get(s), dict) else None
            if not just:
                add("CA602", "warning",
                    f"{s}={parsed[s]:g} / {b}={parsed[b]:g} = {ratio:.1%}，"
                    f"越参数表 {rule['id']} 上界 {rule['max_ratio']:.0%}"
                    f"（{rule['source']}），且无 justification")


def _figure_value(figs: dict, name: str) -> float | None:
    """取一个 figure 的数值；形状不对或负数交给 CA601，这里只做推导。"""
    f = figs.get(name)
    if not isinstance(f, dict):
        return None
    value = _finite_number(f.get("value"))
    if value is None or value < 0:
        return None
    return value


def _figure_justification(figs: dict) -> str | None:
    for name in ("population", "grain_supply", "grain_import"):
        f = figs.get(name)
        if not isinstance(f, dict):
            continue
        j = f.get("justification")
        if isinstance(j, str) and j.strip():
            return j
    return None


def check_world(world: dict, add) -> None:
    """CA603：世界根 `econ.yaml` 的食物比例 × population 对 grain_supply。

    `add(level, rel, message)` 与 core 的 world 规则同签名。配置错误报 error；
    缺口报 warning。没有 `econ.yaml` 时整条规则沉默（缺数据不报错）。
    """
    root = world.get("root")
    if root is None:
        return
    path = Path(root) / ECON_CONFIG
    if not path.exists():
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 —— YAML 解析错误要变成一条可读的 CA603
        add("error", ECON_CONFIG, f"{ECON_CONFIG} 解析失败：{e}")
        return
    if not isinstance(data, dict) or not isinstance(data.get("params"), dict):
        add("error", ECON_CONFIG, f"{ECON_CONFIG} 必须有 `params` 映射")
        return
    param = data["params"].get(FOOD_PARAM)
    if not isinstance(param, dict):
        add("error", ECON_CONFIG,
            f"{ECON_CONFIG} 缺 `params.{FOOD_PARAM}`（每人每日口粮比例）")
        return
    value, unit = param.get("value"), param.get("unit")
    ratio = _finite_number(value)
    if ratio is None or ratio <= 0:
        add("error", ECON_CONFIG,
            f"`params.{FOOD_PARAM}.value` 必须是有限正数，实际 {value!r}")
        return
    if not isinstance(unit, str) or not unit.strip():
        add("error", ECON_CONFIG,
            f"`params.{FOOD_PARAM}.unit` 必须是非空字符串，实际 {unit!r}")
        return

    for e in world.get("all_entries", []):
        figs = e.meta.get("figures")
        if not isinstance(figs, dict):
            continue
        population = _figure_value(figs, "population")
        supply = _figure_value(figs, "grain_supply")
        if population is None or supply is None:
            continue  # 缺数据不报错：世界永远是大部未量化的
        if "grain_import" not in figs:
            imported = 0.0
        else:
            imported = _figure_value(figs, "grain_import")
            if imported is None:
                continue  # 形状坏的 import 交给 CA601，别在这里伪造缺口
        need = population * ratio
        if supply + imported >= need:
            continue
        if _figure_justification(figs):
            continue  # 偏差合法化：有理由就放行
        add("warning", e.rel,
            f"食物缺口：population={population:g} × {FOOD_PARAM}={ratio:g} "
            f"= 需求 {need:g}，grain_supply={supply:g} + grain_import={imported:g} "
            f"= {supply + imported:g}，缺 {need - supply - imported:g}；"
            f"补 grain_import 或写 justification 放行")
