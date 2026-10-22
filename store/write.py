"""存储层 · 写入（init / new / link）。

人怎么把东西**放进去**：建世界仓库、建卡、连线。

**写入是「改结构」，不是「塞文本」。** 旧版 `link` 拿正则往 frontmatter 里插三行，它对
「找到的那一行到底是不是那个键」「这个键出现了几次」「已有条目用的什么缩进」一无所知，
于是三种合法的 YAML 写法下它会把卡写坏或者把边写丢——**同时打印「已连线」**。现在：

1. 键的位置由 YAML 解析器给（不是正则猜的），重复键直接拒绝；
2. 在那个位置做**最小改动**：其它行、注释、缩进、围栏字节、正文一个字节不动；
3. **写完先自己读一遍**：重新解析，比对「旧结构 + 这一条边」。不一致就退到「整块
   重排」再验一次；还不一致就拒绝写入并报错。

宁可拒绝，不许写坏——这条优先级高于「diff 小到能被人评审」。后者现在是副产品，
不是目的：最小改动路径保住 diff，重排路径会在输出里明说「注释与键序会被重排」。

**理论是参数，不是常量**：本层不知道哪些 `layer` 或 `kind` 值正当。调用方（canonlint.py）
把它们作为 `layer_choices` / `kind_choices` 传进来。存储层只负责「按你说的词表拒绝错值」，
换成别的词表照样工作。
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Container, Sequence
from datetime import date
from pathlib import Path

import yaml

from .layout import TYPE_DIRS, collect
from .model import Entry, EVENT_FIELDS
from .parse import FRONTMATTER_RE, ID_RE, parse_text

# 陈旧临时文件的清理门槛：同目录 mkstemp 出来的 `.canonlint-*.tmp`，若进程被 SIGKILL
# 就会永远留在 entries/ 里。它们不会被当成条目（后缀不是 .md），但没人希望世界仓库里
# 慢慢积一堆垃圾。
_TMP_PREFIX = ".canonlint-"
_TMP_SUFFIX = ".tmp"
_TMP_STALE_SECONDS = 3600


def _atomic_write(path: Path, text: str) -> None:
    """同目录临时文件 + `os.replace`：写到一半被杀不会留下半个条目。

    三件以前会静默做错的事：**写穿符号链接**（`os.replace(tmp, link)` 会把链接换成
    普通文件，世界外的目标留在旧内容，两份分叉）、**保留文件模式**（mkstemp 建的是
    0600，一次 link 把 0644/0755 全改掉）、**只读文件要说出来**（Unix 允许「目录可写」
    时替换只读文件，无声把一个 0444 的卡换掉）。
    """
    target = path.resolve()  # 顺着符号链接写真正的文件，别替换链接本身
    try:
        st = target.stat()
    except OSError as e:
        raise OSError(f"{path}: 无法读取文件状态（{e}）") from e
    if not (st.st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)):
        raise OSError(f"{path}: 文件是只读的，拒绝改写（先去掉只读位再跑）")
    _sweep_stale_tmp(target.parent)
    try:
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=_TMP_PREFIX,
                                   suffix=_TMP_SUFFIX)
    except OSError as e:
        raise OSError(f"{target.parent}: 无法在此目录建临时文件（{e}）") from e
    try:
        # newline="" —— 不做行尾翻译，写进去的字节就是我们要的字节
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.chmod(tmp, stat.S_IMODE(st.st_mode))
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _sweep_stale_tmp(directory: Path) -> None:
    """清掉上个进程被 SIGKILL 留下的一次性临时文件（只碰自己的前缀与后缀）。"""
    cutoff = time.time() - _TMP_STALE_SECONDS
    try:
        candidates = list(directory.iterdir())
    except OSError:
        return
    for p in candidates:
        if not (p.name.startswith(_TMP_PREFIX) and p.name.endswith(_TMP_SUFFIX)):
            continue
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            continue


@contextlib.contextmanager
def _world_lock(root: Path):
    """给「读—改—写」上把进程间锁：两个 `link` 同时跑会各读旧内容、各写一遍，丢掉一条边。

    锁文件放系统临时目录（不往世界仓库里扔东西），用世界根路径的散列命名。
    拿不到 fcntl（非 Unix）就退化成不锁——并行写入不是默认用法，退化比报错好。
    """
    key = hashlib.sha1(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"canonlint-{key}.lock"
    try:
        fh = open(lock_path, "a+", encoding="utf-8")
    except OSError:
        yield
        return
    try:
        try:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        try:
            fh.close()
        except OSError:
            pass


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


def _git_dir(root: Path) -> Path | None:
    """真正的 git 目录。`.git` 可能是**文件**（`git worktree` / submodule），里面一行
    `gitdir: <路径>`——只判 `is_dir()` 的话，worktree 里 `init` 会静默装不上钩子，
    而它提示用户「git init 后重跑」也永远不会成功。
    """
    dot = root / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():
        try:
            first = dot.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        except (OSError, IndexError):
            return None
        if first.startswith("gitdir:"):
            cand = first.split(":", 1)[1].strip()
            path = Path(cand)
            return path if path.is_absolute() else (root / path).resolve()
    return None


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
    gitdir = _git_dir(root)
    if gitdir is not None:
        hook = gitdir / "hooks/pre-commit"
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
                print(f"原有 pre-commit 钩子已备份到 {backup}")
            else:
                print(f"警告：原有 pre-commit 钩子已被覆盖过一次，备份仍在 "
                      f"{backup}（本次未再备份）")
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
            *, layer_choices: Sequence[str], fields: dict | None = None) -> int:
    """建卡：生成合法 frontmatter，用户只管写正文。交互问答仅在 TTY 下启用。

    `fields` 是事件流水与断言字段（when/event_kind/腿/owns 等），白名单
    就是存储层的 EVENT_FIELDS——别的键一律拒绝（写出去也是 CA106）。"""
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

    # 用 YAML 序列化，不用字符串拼接：标题里的 `#` 之后会被无声吃掉、冒号会直接产出
    # 一张坏卡（`title: 灰港：北方` 就是非法 YAML）。yaml 会自己把这类值加引号。
    meta: dict = {
        "id": entry_id, "title": title, "type": type_, "author": author,
        # 写成字符串：契约把 date 定义成 ISO 字符串，而 YAML 会把没引号的日期解成
        # datetime.date。工具自己产出的卡不该违反自己的契约（CA103 两种都收）。
        "date": date.today().isoformat(), "status": "draft",
        "load_bearing": bool(load_bearing),
    }
    if load_bearing:
        meta["layer"] = layer
    if fields:
        # owns 是断言但走关系字段面（LEGACY_RELATION_FIELDS），这里一并放行
        allowed = set(EVENT_FIELDS) | {"owns"}
        unknown = sorted(set(fields) - allowed)
        if unknown:
            print(f"error: 不认识的字段 {unknown}（事件/断言字段只有 {sorted(allowed)}）",
                  file=sys.stderr)
            return 2
        meta.update(fields)
    meta.update({"canon_refs": [], "conflicts_with": [], "depends_on": [],
                 "superseded_by": None, "ai_assisted": False})
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False,
                        default_flow_style=False)

    path = root / "entries" / TYPE_DIRS[type_] / f"{entry_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # id 索引查不到不等于路是空的：同路径可能有 id 写坏、id 不同、或手写的文件。
    # 无条件写下去会把它静默吃掉（然后世界多出几条悬空引用），所以这里最后再挡一道。
    # `lexists` 而不是 `exists`：悬空的符号链接 also counts——顺着它写会把卡建到世界外。
    if os.path.lexists(path):
        if path.is_symlink() and not path.exists():
            print(f"error: {path.relative_to(root)} 是一个**悬空的符号链接**，"
                  f"顺着它写会把卡建到世界外面去；请先删掉这个链接", file=sys.stderr)
            return 1
        print(f"error: {path.relative_to(root)} 已存在，拒绝覆盖"
              f"（若那是同一条目请换 id，或先确认它该不该留）", file=sys.stderr)
        return 1
    try:
        path.write_text(f"---\n{fm}---\n\n（正文 200 字起步）\n", encoding="utf-8")
    except OSError as e:
        print(f"error: 建卡失败：{e}", file=sys.stderr)
        return 2
    print(f"已建卡: {path.relative_to(root)}（draft）")
    if load_bearing:
        print(f"提示: 用 canonlint link {entry_id} <它靠谁养> --kind fiscal 连线")
    return 0


# ---- 连线：结构级最小改动 ----------------------------------------------------


def _read_file(path: Path) -> tuple[str, str, str]:
    """读原始字节并保留行尾：返回（正文, BOM, 该文件的行尾符）。

    `read_text()` 会把 CRLF / 裸 CR 统一成 LF，写回时就再也还原不了——一次 link 等于
    一次全文件行尾归一，diff 里全是行尾变化。这里按字节解码，行尾只用于生成新行。
    """
    raw = path.read_bytes()
    bom = ""
    if raw.startswith(b"\xef\xbb\xbf"):
        bom = "\ufeff"
        raw = raw[3:]
    text = raw.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else ("\r" if "\r" in text else "\n")
    return text, bom, nl


def _dep_block(dep: dict, nl: str, indent: int) -> str:
    pad = " " * indent
    return (f"{pad}- id: {dep['id']}{nl}"
            f"{pad}  kind: {dep['kind']}{nl}"
            f"{pad}  critical: {'true' if dep['critical'] else 'false'}")


def _dep_span(fm_text: str):
    """`depends_on` 这个键在 frontmatter 文本里的精确位置（来自 YAML 解析器，不是正则）。

    返回 `(kind, value_node, start, end)`：
    - `("absent", None, None, None)`：没有这个键；
    - `("block", node, None, None)`：块序列，往最后一个元素后面插；
    - `("span", node, start, end)`：值占一段（`[]` 或空），用整块替换。
    """
    try:
        root = yaml.compose(fm_text)
    except (yaml.YAMLError, RecursionError):
        return "absent", None, None, None
    if not isinstance(root, yaml.MappingNode):
        return "absent", None, None, None
    for key_node, value_node in root.value:
        if not isinstance(key_node, yaml.ScalarNode) or key_node.value != "depends_on":
            continue
        if isinstance(value_node, yaml.SequenceNode):
            if value_node.flow_style or not value_node.value:
                return "span", value_node, value_node.start_mark.index, value_node.end_mark.index
            return "block", value_node, None, None
        if isinstance(value_node, yaml.ScalarNode) and value_node.value in ("", None):
            return "span", value_node, value_node.start_mark.index, value_node.end_mark.index
        return "other", value_node, None, None
    return "absent", None, None, None


def _splice(text: str, m, new_fm: str) -> str:
    """只替换 frontmatter 分组：开场围栏那一行、闭合围栏那一行、正文全部原样保留。"""
    return text[:m.start(1)] + new_fm + text[m.end(1):]


def _dump_meta(meta: dict, nl: str) -> str:
    return yaml.safe_dump(meta, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, line_break=nl)


def _verify(text: str, rel: str, want_meta: dict, want_edge: dict) -> bool:
    """写完自检：把写出来的文本重新解析，确认「旧结构 + 这条边」真的在里面。

    这是整条写入路径的兜底：最小改动插错了位置（缩进、重复键、多行标量里的假键）
    在文本上看不出来，但解析结果会不一样。自检不过就不写盘。
    """
    got = parse_text(text, rel)
    if got.parse_error or got.duplicate_keys:
        return False
    if got.meta != want_meta:
        return False
    entry = got.as_entry(Entry)
    if entry.parse_error:
        return False
    for edge in entry.edges_of("depends_on"):
        if (edge.target == want_edge["id"]
                and edge.attrs.get("kind") == want_edge["kind"]
                and edge.attrs.get("critical") is want_edge["critical"]):
            return True
    return False


def _insert_dep(fm_text: str, dep: dict, nl: str):
    """在 `depends_on` 上做最小改动。返回（新 frontmatter 文本, 是否丢注释）或 None。

    返回 None 表示这个形态没法安全地做文本手术（行内非空列表、标量、映射……），
    交给调用方退到整块重排。
    """
    kind, node, start, end = _dep_span(fm_text)
    if kind == "absent":
        head = fm_text if fm_text.endswith(nl) else fm_text + nl
        return head + "depends_on:" + nl + _dep_block(dep, nl, 2) + nl
    if kind == "block":
        last = node.value[-1]
        at = last.end_mark.index
        indent = node.value[0].start_mark.column
        return fm_text[:at] + nl + _dep_block(dep, nl, indent) + fm_text[at:]
    if kind == "span":
        # `[]` 或 `depends_on:` 之后什么都没有：整段值换成块序列
        return fm_text[:start] + nl + _dep_block(dep, nl, 2).rstrip("\r\n") + fm_text[end:]
    return None


def cmd_link(root: Path, src: str, dst: str, kind: str, critical: bool,
             *, kind_choices: Container[str]) -> int:
    """连线：给 src 的 depends_on 追加一条供养边。**改结构，不塞文本**（见模块 docstring）。"""
    all_entries, index, _ = collect(root)

    def find(eid: str) -> str | None:
        """返回 None=正常；否则为错误消息。"""
        if eid in index:
            return None
        for x in all_entries:
            # 解析失败时 meta 是空的，id 恒为 None——所以按**文件名**认。
            # 以前这里查 `x.id == eid`，那条分支永远进不去，作者只会看到「不存在」。
            if x.parse_error and x.path.stem == eid:
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

    dep = {"id": dst, "kind": kind, "critical": bool(critical)}

    with _world_lock(root):
        # 锁里重读：并发写入时，collect 出来的那份可能已经是旧的了
        e = index[src]
        text, bom, nl = _read_file(e.path)
        m = FRONTMATTER_RE.match(text)
        if m is None:
            print("error: 该条目没有可解析的 frontmatter，无法连线，请手动编辑",
                  file=sys.stderr)
            return 2
        before = parse_text(text, e.rel)
        if before.duplicate_keys:
            print(f"error: 这张卡的 frontmatter 有重复字段 "
                  f"{sorted(set(before.duplicate_keys))}：YAML 只保留最后一个，"
                  f"先修掉重复再连线（否则边可能写进被覆盖的那一个）", file=sys.stderr)
            return 2

        entry = before.as_entry(Entry)
        # 去重要按**规范化后的边**判：只查 depends_on 具名字段会漏掉规范形
        # `relations: [{type: depends_on, target: …}]` 里已经写下的同一条边。
        if any(r.target == dst and r.attrs.get("kind") == kind
               for r in entry.edges_of("depends_on")):
            print(f"边已存在: {src} --{kind}--> {dst}，不重复添加")
            return 0
        if entry.depends_on_requires_annotations is False:
            # classlint 口径下 depends_on 可以只写 id，但 canonlint 侧要求 kind/critical
            # 齐全，所以写入端一律写全三项——两种口径都合法。
            pass

        old_meta = dict(before.meta)
        want_meta = dict(old_meta)
        want_meta["depends_on"] = list(old_meta.get("depends_on") or []) + [dict(dep)]

        new_fm = _insert_dep(m.group(1), dep, nl)
        how = "最小改动"
        if new_fm is not None:
            candidate = _splice(text, m, new_fm)
            if not _verify(candidate, e.rel, want_meta, dep):
                new_fm = None
        if new_fm is None:
            # 退到整块重排：结构一定对，代价是 frontmatter 里的注释与键序会被重排。
            new_fm = _dump_meta(want_meta, nl).rstrip("\r\n")
            candidate = _splice(text, m, new_fm)
            how = "整块重排"
            if not _verify(candidate, e.rel, want_meta, dep):
                print("error: 写入自检失败（重排后的内容与预期不一致），拒绝写入磁盘；"
                      "请手动编辑这条边", file=sys.stderr)
                return 2

        try:
            _atomic_write(e.path, bom + candidate)
        except OSError as err:
            print(f"error: 写入失败：{err}", file=sys.stderr)
            return 2
    print(f"已连线: {src} --{kind}{'(critical)' if critical else ''}--> {dst}")
    if how == "整块重排":
        print("注意: 这张卡的 frontmatter 形态不支持原地插入，已整块重排"
              "（注释与键序可能变化）")
    print("记得跑 canonlint 检查这条边是否合法（层级方向/环/状态）")
    return 0
