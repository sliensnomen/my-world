#!/usr/bin/env python3
"""classlint — 马克思主义政治经济学审计工具 · Sprint 0 基础层

用马克思主义政治经济学的规则，审计一个虚构世界的结构。
Git + Markdown 是唯一事实来源：条目 = codex/ 下一个带 YAML frontmatter 的 Markdown 文件。

用法:
  classlint.py init [目录]        初始化世界仓库（目录结构 + classlint.yaml + git）
  classlint.py check [目录]       读取全部条目并输出结构化数据（--json 机器可读）
退出码: 0=正常 1=条目存在错误 2=用法/环境错误
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VERSION = "0.1"

# ---- 实体 ID 规范（Sprint 0）-----------------------------------------------
# 小写字母/数字/连字符，全库唯一，一旦发布永不更改、永不复用（同 WGP 惯例）。
ID_RE = re.compile(r"^[a-z0-9-]+$")

ENTRY_ROOT = "codex"  # 条目（实体）唯一位置；状态与身份只认 frontmatter，目录纯组织
SKIP_DIRS = {".git"}

CONFIG_SKELETON = """\
# classlint 世界配置
name: {name}
classlint: "{version}"   # 创建工具版本
rules: []                # 启用的规则包（Sprint 2 起）
"""

ENTITIES_SKELETON = """\
# 实体注册表：稳定 ID 与别名。
# 条目正文可用别名指代实体，审计时统一解析到这里的稳定 ID（别名解析 Sprint 1 实现）。
# 格式：
# entities:
#   gray-harbor:           # 稳定 ID（= 条目 frontmatter 的 id）
#     aliases: [灰港, 灰港城]
entities: {{}}
"""

# init 创建的目录（空目录放 .gitkeep，git 不跟踪空目录）
WORLD_DIRS = [
    "rules",
    "lore",
    "codex/characters",
    "codex/locations",
    "codex/factions",
    "stories",
    "timeline",
    "records",
]

# ---- 数据模型与解析（自 canonlint 抽取）--------------------------------------

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


@dataclass
class Entry:
    """一个条目 = 一个带 YAML frontmatter 的 Markdown 文件。"""
    path: Path
    rel: str
    meta: dict
    body: str
    parse_error: str | None = None

    @property
    def id(self) -> str | None:
        v = self.meta.get("id")
        return v if isinstance(v, str) else None


@dataclass
class Finding:
    level: str  # error | warning
    entry: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:7s} {self.entry}: {self.message}"


def parse_entry(path: Path, root: Path) -> Entry:
    rel = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return Entry(path, rel, {}, text,
                     parse_error="缺少 frontmatter（文件须以 --- 包裹的 YAML 头开始）")
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return Entry(path, rel, {}, "", parse_error=f"frontmatter YAML 解析失败: {e}")
    if not isinstance(meta, dict):
        return Entry(path, rel, {}, "", parse_error="frontmatter 必须是键值映射")
    return Entry(path, rel, meta, text[m.end():])


def collect(root: Path) -> tuple[list[Entry], dict[str, Entry], list[Finding]]:
    """扫描 codex/ 下全部条目。返回 (全部条目, id 索引, 发现)。
    重复 id：首个（按路径序）入索引，后续不入索引。"""
    codex = root / ENTRY_ROOT
    entries: list[Entry] = []
    if codex.is_dir():
        for p in sorted(codex.rglob("*.md")):
            if SKIP_DIRS & set(p.relative_to(root).parts):
                continue
            entries.append(parse_entry(p, root))

    index: dict[str, Entry] = {}
    findings: list[Finding] = []
    for e in entries:
        if e.parse_error:
            findings.append(Finding("error", e.rel, e.parse_error))
            continue
        if not e.id:
            findings.append(Finding("error", e.rel, "缺少 id 字段"))
            continue
        if not ID_RE.match(e.id):
            findings.append(Finding("error", e.rel,
                                    f"id={e.id!r} 非法（仅允许小写字母/数字/连字符）"))
            continue
        if e.id in index:
            findings.append(Finding("error", e.rel,
                                    f"id `{e.id}` 重复：{index[e.id].rel} 与 {e.rel}"))
        else:
            index[e.id] = e
    return entries, index, findings


# ---- 命令 --------------------------------------------------------------------


def cmd_init(root: Path) -> int:
    """初始化世界仓库：目录结构 + classlint.yaml + entities.yaml + git。"""
    root.mkdir(parents=True, exist_ok=True)
    cfg = root / "classlint.yaml"
    if cfg.exists():
        print(f"error: {root} 已是 classlint 世界仓库（classlint.yaml 已存在）",
              file=sys.stderr)
        return 1
    for d in WORLD_DIRS:
        sub = root / d
        sub.mkdir(parents=True, exist_ok=True)
        keep = sub / ".gitkeep"
        if not any(sub.iterdir()):
            keep.touch()
    cfg.write_text(CONFIG_SKELETON.format(name=root.name, version=VERSION),
                   encoding="utf-8")
    (root / "codex" / "entities.yaml").write_text(ENTITIES_SKELETON, encoding="utf-8")
    if not (root / ".git").is_dir():
        r = subprocess.run(["git", "init"], cwd=root, capture_output=True)
        if r.returncode == 0:
            print("git 仓库已初始化")
        else:
            print("提示：git init 失败，请手动执行", file=sys.stderr)
    print(f"世界仓库已初始化: {root}")
    return 0


def cmd_check(root: Path, as_json: bool) -> int:
    """读取全部条目，输出结构化数据。"""
    if not (root / "classlint.yaml").is_file():
        print(f"error: {root} 不是 classlint 世界仓库（缺 classlint.yaml）",
              file=sys.stderr)
        return 2
    entries, index, findings = collect(root)
    errors = [f for f in findings if f.level == "error"]

    if as_json:
        print(json.dumps({
            "classlint_version": VERSION,
            "entries": [
                {"id": e.id, "path": e.rel,
                 "meta": {k: v for k, v in e.meta.items()},
                 "body_chars": len(e.body.strip())}
                for e in entries if not e.parse_error
            ],
            "findings": [{"level": f.level, "entry": f.entry, "message": f.message}
                         for f in findings],
        }, ensure_ascii=False, indent=2, default=str))
    else:
        for e in entries:
            if e.parse_error:
                continue
            type_ = e.meta.get("type", "(无 type)")
            print(f"条目 {e.id or '(无 id)':24s} type={type_!s:12s} "
                  f"正文 {len(e.body.strip())} 字  {e.rel}")
        for f in findings:
            print(f)
        print(f"\n{len(entries)} 个条目 | {len(index)} 个有效 id | {len(errors)} 错误")
    return 1 if errors else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=f"classlint — 马克思主义政治经济学审计工具 v{VERSION}（Sprint 0 基础层）")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p_init = sp.add_parser("init", help="初始化世界仓库")
    p_init.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_check = sp.add_parser("check", help="读取全部条目并输出结构化数据")
    p_check.add_argument("root", type=Path, nargs="?", default=Path("."))
    p_check.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    root = args.root.resolve()
    if args.cmd == "init":
        return cmd_init(root)
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2
    return cmd_check(root, args.json)


if __name__ == "__main__":
    sys.exit(main())
