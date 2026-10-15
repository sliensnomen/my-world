"""存储层 · 写入（init / new / link）。

人怎么把东西**放进去**：建世界仓库、建卡、连线。写入是文本级的（原地插入、不重排
frontmatter），所以 diff 小到能被人评审——这正是 PR 流程要求的。

**理论是参数，不是常量**：本层不知道哪些 `layer` 或 `kind` 值正当。调用方（canonlint.py）
把它们作为 `layer_choices` / `kind_choices` 传进来。存储层只负责「按你说的词表拒绝错值」，
换成别的词表照样工作。
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from collections.abc import Container, Sequence
from datetime import date
from pathlib import Path

from .layout import TYPE_DIRS, collect
from .model import FRONTMATTER_RE, ID_RE


def _atomic_write(path: Path, text: str) -> None:
    """同目录临时文件 + `os.replace`：写到一半被杀不会留下半个条目。"""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".canonlint-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

CONSTITUTION_SKELETON = """# 世界宪章 v0.1

protocol: WGP 1.0

## Tone 锚（三个参照作品）
1. 
2. 
3. 

## 质量标准
- 信息密度 / 咬合度 / 留钩子

## 禁项
- 现实政治影射 / 成人内容

## 治理程序
- 升格：评审通过，理由引用本宪章条款
- 降级：不删稿，填 superseded_by，72 小时上诉期
- 恢复：默认 archived → trial → canon（本宪章未声明快速通道）

## AI 条款
- AI 产出永不入 canon；辅助须标 ai_assisted: true
"""


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s


def _ask(prompt: str, default: str = "") -> str:
    """交互式提问；非 TTY 环境（CI/管道）直接用默认值，绝不阻塞。"""
    if not sys.stdin.isatty():
        return default
    return input(prompt).strip() or default


def cmd_init(root: Path, *, exe: str) -> int:
    """初始化世界仓库：目录结构 + 宪章骨架 + pre-commit 钩子。
    目录约定：entries/{type}/ 唯一条目位置；状态只认 frontmatter（协议 §2）。

    `exe` 是钩子该调用的命令——由 CLI 决定（`canonlint` 在 PATH 里就用它，
    否则用 canonlint.py 的绝对路径）。存储层不该猜自己是怎么被叫起来的。
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "templates").mkdir(exist_ok=True)
    for sub in TYPE_DIRS.values():
        (root / "entries" / sub).mkdir(parents=True, exist_ok=True)
    con = root / "CONSTITUTION.md"
    if not con.exists():
        con.write_text(CONSTITUTION_SKELETON, encoding="utf-8")
    if (root / ".git").is_dir():
        hook = root / ".git/hooks/pre-commit"
        # .git 在但 hooks/ 不在（别的工具造的仓库、被清过的仓库）——补上，别让 traceback 逃逸
        hook.parent.mkdir(parents=True, exist_ok=True)
        want = ("#!/bin/sh\n"
                f"{exe} \"$(git rev-parse --show-toplevel)\" || exit 1\n")
        # 别人可能已经装了自己的钩子：覆盖前先备份，不静默吃掉别人的东西
        if hook.exists() and hook.read_text(encoding="utf-8", errors="replace") != want:
            backup = hook.with_name("pre-commit.bak")
            if not backup.exists():
                backup.write_text(hook.read_text(encoding="utf-8", errors="replace"),
                                  encoding="utf-8")
                backup.chmod(0o755)
                print(f"原有 pre-commit 钩子已备份到 {backup.relative_to(root)}")
            else:
                print(f"警告：原有 pre-commit 钩子已被覆盖过一次，备份仍在 "
                      f"{backup.relative_to(root)}（本次未再备份）")
        hook.write_text(want, encoding="utf-8")
        hook.chmod(0o755)
        print("pre-commit 钩子已装（审计不过则拒提交）")
    else:
        print("提示：git init 后重跑本命令可装 pre-commit 钩子")
    print(f"世界仓库已初始化: {root}")
    print("下一步: canonlint new location 灰港")
    return 0


def cmd_new(root: Path, type_: str | None, title: str | None,
            entry_id: str | None, author: str | None = None,
            load_bearing: bool = False, layer: str | None = None,
            *, layer_choices: Sequence[str]) -> int:
    """建卡：生成合法 frontmatter，用户只管写正文。交互问答仅在 TTY 下启用。"""
    tty = sys.stdin.isatty()
    if type_ is None:
        type_ = _ask(f"类型 {sorted(TYPE_DIRS)}: ")
    if type_ not in TYPE_DIRS:
        print(f"error: type={type_!r} 非法（非交互环境请传位置参数：canonlint new <type> <title>）",
              file=sys.stderr)
        return 2
    if title is None:
        title = _ask("标题: ")
    if not title:
        print("error: 缺少标题（非交互环境请传：canonlint new <type> <title>）", file=sys.stderr)
        return 2
    if entry_id is None:
        guess = slugify(title)
        entry_id = _ask(f"id（小写字母/数字/连字符）{f'[{guess}]' if guess else ''}: ",
                        guess)
    if not entry_id or not ID_RE.match(entry_id):
        print(f"error: id={entry_id!r} 非法或缺失（中文标题请用 --id 指定）", file=sys.stderr)
        return 2

    _, index, _ = collect(root)
    if entry_id in index:
        print(f"error: id `{entry_id}` 已存在（{index[entry_id].rel}）", file=sys.stderr)
        return 1

    if tty and not load_bearing:
        load_bearing = _ask("承重墙条目？[y/N]: ").lower() == "y"
    if author is None:
        author = _ask("署名: ", "anonymous")
    if load_bearing and layer is None and layer_choices:
        layer = _ask(f"层级 {list(layer_choices)}: ")
    if load_bearing and layer not in layer_choices:
        print(f"error: 承重墙条目必须给 layer（{list(layer_choices)}）", file=sys.stderr)
        return 2

    meta_lines = [
        "---", f"id: {entry_id}", f"title: {title}", f"type: {type_}",
        f"author: {author}",
        # 加引号：契约把 date 写成 ISO 字符串，而 YAML 会把没引号的日期解成
        # datetime.date——工具自己产出的卡不该违反自己的契约（CA103 两种都收，
        # 见 canonlint.is_valid_date）。
        f'date: "{date.today().isoformat()}"', "status: draft",
        f"load_bearing: {'true' if load_bearing else 'false'}",
    ]
    if load_bearing:
        meta_lines.append(f"layer: {layer}")
    meta_lines += ["canon_refs: []", "conflicts_with: []", "depends_on: []",
                   "superseded_by: null", "ai_assisted: false", "---", ""]

    path = root / "entries" / TYPE_DIRS[type_] / f"{entry_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # id 索引查不到不等于路是空的：同路径可能有 id 写坏、id 不同、或手写的文件。
    # 无条件写下去会把它静默吃掉（然后世界多出几条悬空引用），所以这里最后再挡一道。
    if path.exists():
        print(f"error: {path.relative_to(root)} 已存在，拒绝覆盖"
              f"（若那是同一条目请换 id，或先确认它该不该留）", file=sys.stderr)
        return 1
    path.write_text("\n".join(meta_lines) + "\n\n（正文 200 字起步）\n", encoding="utf-8")
    print(f"已建卡: {path.relative_to(root)}（draft）")
    if load_bearing:
        print(f"提示: 用 canonlint link {entry_id} <它靠谁养> --kind fiscal 连线")
    return 0


def _insert_dep_text(fm_text: str, dep_block: list[str]) -> str | None:
    """文本级插入 depends_on 条目，不重排 frontmatter、不丢注释。"""
    lines = fm_text.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^depends_on:\s*(\[\])?\s*(#.*)?$", line)
        if not m:
            if re.match(r"^depends_on:\s*\S", line):  # 行内非空值（非法形态），交给 lint 报
                return None
            continue
        if m.group(1):  # 空列表（可带行尾注释）→ 转块列表，注释保留在键行
            comment = f"  {m.group(2)}" if m.group(2) else ""
            lines[i] = f"depends_on:{comment}"
            return "\n".join(lines[:i + 1] + dep_block + lines[i + 1:])
        # 块列表：块尾 = 下一个顶格键；跳过尾部空行后插入
        j = i + 1
        while j < len(lines) and (lines[j].startswith((" ", "-")) or not lines[j].strip()):
            j += 1
        k = j
        while k > i + 1 and not lines[k - 1].strip():
            k -= 1
        return "\n".join(lines[:k] + dep_block + lines[k:])
    return None  # frontmatter 里没有 depends_on 键


def cmd_link(root: Path, src: str, dst: str, kind: str, critical: bool,
             *, kind_choices: Container[str]) -> int:
    """连线：给 src 的 depends_on 追加一条供养边（文本级插入，diff 最小）。"""
    all_entries, index, _ = collect(root)

    def find(eid: str) -> str | None:
        """返回 None=正常；否则为错误消息。"""
        if eid in index:
            return None
        for x in all_entries:
            if x.id == eid and x.parse_error:
                return f"条目 `{eid}` 存在但解析失败：{x.parse_error}"
        return f"条目 `{eid}` 不存在"

    for eid in (src, dst):
        err = find(eid)
        if err:
            print(f"error: {err}", file=sys.stderr)
            return 1
    if kind not in kind_choices and not kind.startswith("x-"):
        print(f"error: kind={kind!r} 须在 {sorted(kind_choices)} 内或带 x- 前缀",
              file=sys.stderr)
        return 2

    e = index[src]
    # 去重要按**规范化后的边**判：只查 depends_on 具名字段会漏掉规范形
    # `relations: [{type: depends_on, target: …}]` 里已经写下的同一条边。
    if any(r.target == dst and r.attrs.get("kind") == kind
           for r in e.edges_of("depends_on")):
        print(f"边已存在: {src} --{kind}--> {dst}，不重复添加")
        return 0

    dep_block = [f"  - id: {dst}", f"    kind: {kind}",
                 f"    critical: {'true' if critical else 'false'}"]
    text = e.path.read_text(encoding="utf-8")
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body = text[len(bom):]
    m = FRONTMATTER_RE.match(body)
    if m is None:
        print("error: 该条目没有可解析的 frontmatter（或带 BOM），"
              "无法文本级插入，请手动编辑", file=sys.stderr)
        return 2
    new_fm = _insert_dep_text(m.group(1), dep_block)
    if new_fm is None:
        print("error: depends_on 形态无法文本级插入（可能是行内列表或键缺失），"
              "请手动编辑该条目", file=sys.stderr)
        return 2
    _atomic_write(e.path, bom + f"---\n{new_fm}\n---\n" + body[m.end():])
    print(f"已连线: {src} --{kind}{'(critical)' if critical else ''}--> {dst}")
    print("记得跑 canonlint 检查这条边是否合法（层级方向/环/状态）")
    return 0
