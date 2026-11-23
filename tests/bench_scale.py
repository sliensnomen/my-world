#!/usr/bin/env python3
"""规模基准（issue #15）：生成合成世界，量审计 / 导出 / 单条读取的耗时。

跑法：python3 tests/bench_scale.py [--entries 200,1000] [--body 4000]
结果用来对照 docs/规模预算.md 的预算；不预设机器性能，输出含条目数与耗时。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import canonlint  # noqa: E402


def make_world(count: int, body_len: int) -> Path:
    td = Path(tempfile.mkdtemp(prefix="bench-"))
    world = td / "w"
    (world / "entries").mkdir(parents=True)
    words = [f"词{k:03d}" for k in range(120)]
    for i in range(count):
        rng = random.Random(i)
        shuffled = words * (body_len // 400 + 1)
        rng.shuffle(shuffled)
        body = " ".join(shuffled)[:body_len]
        (world / "entries" / f"card-{i:05d}.md").write_text(
            f"---\nid: card-{i:05d}\ntitle: 卡{i}\ntype: location\nauthor: t\n"
            f"date: 2026-01-01\nstatus: canon\nload_bearing: false\n"
            f"canon_refs: []\nconflicts_with: []\n"
            f"depends_on:\n  - id: card-{max(0, i - 1):05d}\n    critical: false\n"
            f"ai_assisted: false\n---\n\n{body}\n", encoding="utf-8")
    return world


def bench(count: int, body_len: int) -> dict:
    world = make_world(count, body_len)
    t0 = time.perf_counter()
    all_entries, index, findings, _reports = canonlint.run(world, 0.85, [], packs=[])
    audit_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    packs, _ = canonlint._load_packs([])
    data = canonlint.export_world(world, packs, (), frozenset())
    export_ms = (time.perf_counter() - t0) * 1000
    import serve
    httpd = serve.make_server(world, "127.0.0.1", 0, packs=packs, quiet=True)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    def get_ms(path: str) -> float:
        t = time.perf_counter()
        urllib.request.urlopen(base + path, timeout=120).read()
        return (time.perf_counter() - t) * 1000
    health_cold = get_ms("/api/health")
    health_warm = get_ms("/api/health")
    entry_warm = get_ms("/api/entry/card-00000")
    world_warm = get_ms("/api/world")
    httpd.shutdown()
    # /api/health 与 /api/entry 当前都先做完整导出：量导出就是量它们的主路径。
    return {"entries": count, "body": body_len, "findings": len(findings),
            "audit_ms": round(audit_ms, 1), "export_ms": round(export_ms, 1),
            "health_cold_ms": round(health_cold, 1),
            "health_warm_ms": round(health_warm, 1),
            "entry_warm_ms": round(entry_warm, 1),
            "world_warm_ms": round(world_warm, 1),
            "entries_in_export": len(data["entries"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entries", default="200,1000")
    ap.add_argument("--body", type=int, default=4000)
    args = ap.parse_args()
    rows = [bench(int(n), args.body) for n in args.entries.split(",")]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
