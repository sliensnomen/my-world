"""存储层 · 文件布局与扫描。

世界数据在磁盘上长什么样：哪些目录放条目、哪些目录跳过、一个条目文件叫什么名字，
以及把一棵世界树读成一串 `Entry` 并建立 id 索引。

**不认识理论**：它不知道 `layer` 的值有没有意义、哪条边是承重墙、哪些关系讲得通。
扫描顺序是 `sorted()` 的确定序——同一棵树永远得到同一个结果。
"""
from __future__ import annotations

from pathlib import Path

from .model import Entry, ShapeIssue, parse_entry

# ---- 布局 ------------------------------------------------------------------

ENTRY_DIRS = ("entries", "canon", "sandbox", "archive")  # 条目扫描目录
SKIP_DIRS = {"templates", "scripts", ".git"}
ENTRY_SUFFIX = "*.md"

# 类型 → 目录名。这是**存储事实**（条目的家在哪），不是理论；
# 严格判定器要求的 type 词表今天与它一致，两者若某天需要分开，分离点在这里。
TYPE_DIRS = {"location": "locations", "faction": "factions",
             "character": "characters", "event": "events", "item": "items"}


def root_cards(root: Path) -> list[Path]:
    """根目录级的条目卡：以 frontmatter 围栏（`---`）开头的 `.md`。

    判据是**文件是不是打算当卡片写**，不是「解析得成功」。用「解析得成功」当判据
    会造出新的静默：一张 frontmatter 写坏的根级卡片会被悄悄跳过，连 CA100 都看不到。
    所以只看开头的围栏——`README.md` 这类散文文档（按名字排除）不算卡片，
    围栏在而 frontmatter 坏掉的，一律交给 `parse_entry` 去报。
    """
    out: list[Path] = []
    for path in sorted(root.glob(ENTRY_SUFFIX)):
        if not path.is_file() or path.name.lower() == "readme.md":
            continue  # 同名目录、悬空软链与目录说明都不是条目
        try:
            head = path.read_text(encoding="utf-8-sig")[:3]
        except (OSError, UnicodeDecodeError):
            out.append(path)  # 读不了也让解析器去说，别在这里吞掉
            continue
        if head == "---":
            out.append(path)
    return out


def iter_entry_paths(root: Path) -> list[Path]:
    """按确定序列出所有条目文件（跳过 SKIP_DIRS、同名目录与悬空符号链接）。

    `entries/` 存在时**根目录级的卡片照样要收**：扁平世界只要跑过一次
    `canonlint new` 建出 `entries/`，根目录那张卡就会整批隐身，退出码还是 0
    （评审 blocker）。扁平模式（没有 ENTRY_DIRS）行为不变，仍把根目录下每篇
    `.md` 都交给解析器——那里没有「散文 vs 卡片」的歧义空间。
    """
    dirs = [root / d for d in ENTRY_DIRS if (root / d).is_dir()]
    flat = not dirs
    if flat:
        dirs = [root]
    paths: list[Path] = []
    for d in dirs:
        for p in sorted(d.rglob(ENTRY_SUFFIX)):
            if not p.is_file():
                # rglob("*.md") 也会返回同名目录与悬空符号链接，跳过而非崩溃
                continue
            if SKIP_DIRS & set(p.relative_to(root).parts):
                continue
            paths.append(p)
    if not flat:
        paths.extend(root_cards(root))
    return paths


def looks_like_world(root: Path) -> bool:
    """这个目录看起来是不是一个世界？判据只看**布局**（不涉及理论）。

    有 `entries/`（或 canon/sandbox/archive）就是；否则要求根目录里至少有一篇
    条目卡（见 `root_cards`）。两者都没有就是走错了地方——拿一个普通目录
    （仓库根、docs/）当世界审，会把每篇文档都当成坏条目，吐几百条假错误，
    而真正的答案只是「你指错目录了」（评审：752 条）。
    """
    return bool(any((root / d).is_dir() for d in ENTRY_DIRS) or root_cards(root))


def collect(root: Path) -> tuple[list[Entry], dict[str, Entry], list[ShapeIssue]]:
    """扫描世界树。返回 (全部条目, id索引, 索引期发现)。
    重复 id：首个（按路径序）入索引，后续的不入索引但仍参与结构检查。"""
    all_entries = [parse_entry(p, root) for p in iter_entry_paths(root)]

    index: dict[str, Entry] = {}
    issues: list[ShapeIssue] = []
    for e in all_entries:
        if e.parse_error or not e.id:
            continue
        if e.id in index:
            issues.append(ShapeIssue(
                "CA105", e.rel,
                f"id `{e.id}` 重复：{index[e.id].rel} 与 {e.rel}"
                "（后者不入索引，别人引用这个 id 时指的是前者；它自己的引用照旧检查）"))
        else:
            index[e.id] = e
    return all_entries, index, issues
