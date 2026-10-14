#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WGP 只读接口：把世界数据用 HTTP 交给前端。

    python3 serve.py [世界目录] [--host 127.0.0.1] [--port 8000] [--pack econ]

路由
    GET /                  一页说明（不是界面）
    GET /api/health        存活 + 版本号
    GET /api/world         整个世界（与 `canonlint export` 同一份数据）
    GET /api/entry/<id>    单个条目 + 跟它相关的边（进的和出的）
    GET /api/raw/<path>    世界目录里的原始文件（只读，给"看原文"用）
    GET /web/...           ./web 目录下的静态文件（前端可以放这儿，同源，省掉 CORS）

规矩
    · 只读：任何非 GET/HEAD 一律 405。
    · 每次请求重新读盘：Markdown 是唯一真相，改完文件刷新页面就是新数据。
    · 不缓存、不写盘、不留时间戳 —— 同一份数据两次请求字节一致。
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import canonlint  # noqa: E402  （同一个目录里的参考实现）

WEB_DIR = HERE / "web"
ROUTES = ["/", "/api/health", "/api/world", "/api/entry/<id>", "/api/raw/<path>", "/web/..."]

_CTYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}


def _inside(target: Path, base: Path) -> bool:
    """target 是不是就在 base 里面（防 ../ 穿越）。"""
    return target == base or base in target.parents


class Handler(BaseHTTPRequestHandler):
    server_version = "wgp-serve/" + canonlint.PROTOCOL_VERSION
    protocol_version = "HTTP/1.1"

    # ---- 基础设施 -------------------------------------------------------

    def log_message(self, fmt, *args):  # 默认那行日志太吵，压成一行
        if not getattr(self.server, "quiet", False):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _export(self) -> dict:
        return canonlint.export_world(self.server.wgp_root, self.server.wgp_packs,
                                      (), self.server.wgp_extra_known)

    # ---- 路由 -----------------------------------------------------------

    def do_GET(self):  # noqa: N802 （http.server 的命名）
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._index()
        if path == "/api/health":
            data = self._export()
            return self._json(200, {
                "ok": True,
                "world": self.server.wgp_root.name,
                "protocol_version": data["protocol_version"],
                "contract_version": data["contract_version"],
                "counts": data["counts"],
            })
        if path == "/api/world":
            return self._json(200, self._export())
        if path.startswith("/api/entry/"):
            return self._entry(path[len("/api/entry/"):])
        if path.startswith("/api/raw/"):
            return self._raw(path[len("/api/raw/"):])
        if path == "/web" or path.startswith("/web/"):
            return self._static(path)
        return self._json(404, {"error": f"没有这个路由: {path}", "routes": ROUTES})

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def _readonly(self):  # 写操作一律拒绝
        self._json(405, {"error": "只读接口：只能用 GET/HEAD", "routes": ROUTES})

    do_POST = do_PUT = do_DELETE = do_PATCH = _readonly

    # ---- 各个出口 -------------------------------------------------------

    def _entry(self, entry_id: str) -> None:
        data = self._export()
        entry = next((e for e in data["entries"] if e["id"] == entry_id), None)
        if entry is None:
            broken = [e["path"] for e in data["entries"] if e.get("parse_error")]
            return self._json(404, {
                "error": f"没有这个条目: {entry_id}",
                "hint": "读不出来的文件没有 id，用 /api/world 里的 parse_error 条目按 path 找",
                "unparsed": broken,
            })
        edges = [r for r in data["relations"]
                 if r["source"] == entry_id or r["target"] == entry_id]
        return self._json(200, {
            "protocol_version": data["protocol_version"],
            "contract_version": data["contract_version"],
            "entry": entry,
            "relations": edges,
        })

    def _raw(self, rel: str) -> None:
        target = (self.server.wgp_root / rel.lstrip("/")).resolve()
        if not _inside(target, self.server.wgp_root) or not target.is_file():
            return self._json(404, {"error": f"世界目录里没有这个文件: {rel}"})
        ctype = _CTYPES.get(target.suffix.lower(), "text/plain; charset=utf-8")
        return self._send(200, target.read_bytes(), ctype,
                          {"X-WGP-Path": str(target.relative_to(self.server.wgp_root))})

    def _static(self, path: str) -> None:
        rel = path[len("/web/"):] if path.startswith("/web/") else ""
        target = (WEB_DIR / (rel or "index.html")).resolve()
        if not WEB_DIR.is_dir() or not _inside(target, WEB_DIR) or not target.is_file():
            return self._json(404, {
                "error": f"web/ 里没有这个文件: {rel or 'index.html'}",
                "hint": "把前端文件放进 canonlint/web/ 就能用同源地址打开：/web/index.html",
            })
        return self._send(200, target.read_bytes(),
                          _CTYPES.get(target.suffix.lower(), "application/octet-stream"))

    def _index(self) -> None:
        data = self._export()
        c = data["counts"]
        rows = "".join(
            f"<tr><td><code>{r}</code></td></tr>" for r in ROUTES)
        html = f"""<!doctype html>
<html lang="zh"><meta charset="utf-8">
<title>WGP 只读接口</title>
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:44rem;margin:3rem auto;padding:0 1rem}}
code{{background:#f2f2f2;padding:.1em .3em;border-radius:3px}}td{{padding:.2rem 0}}</style>
<h1>WGP 只读接口</h1>
<p>世界：<code>{self.server.wgp_root}</code></p>
<p>{c['entries']} 个条目（{c['unparsed']} 个读不出来）｜{c['relations']} 条边（{c['dangling']} 条指不到人）｜
{c['errors']} 错误 / {c['warnings']} 警告</p>
<p>协议 <code>{data['protocol_version']}</code>，数据合同 <code>{data['contract_version']}</code></p>
<table>{rows}</table>
<p>这不是界面 —— 界面由前端写。前端文件放进 <code>canonlint/web/</code>，然后用
<code>/web/index.html</code> 打开，和接口同源。</p>
</html>
""".encode("utf-8")
        return self._send(200, html, "text/html; charset=utf-8")


def make_server(root: Path, host: str, port: int, packs=(), extra_known=frozenset(),
                quiet: bool = False) -> ThreadingHTTPServer:
    """起一个 server（不阻塞）。端口给 0 = 让系统随便挑一个空端口。"""
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.wgp_root = root.resolve()            # type: ignore[attr-defined]
    httpd.wgp_packs = tuple(packs)             # type: ignore[attr-defined]
    httpd.wgp_extra_known = extra_known        # type: ignore[attr-defined]
    httpd.quiet = quiet                        # type: ignore[attr-defined]
    httpd.daemon_threads = True
    return httpd


def serve(root: Path, host: str, port: int, packs=(), extra_known=frozenset(),
          quiet: bool = False) -> None:
    httpd = make_server(root, host, port, packs, extra_known, quiet)
    real_port = httpd.server_address[1]
    print(f"WGP 只读接口就绪：http://{host}:{real_port}/api/world")
    print(f"世界目录：{httpd.wgp_root}（改了 Markdown 刷新页面就是新数据）")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停了。")
    finally:
        httpd.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=f"WGP 只读接口 v{canonlint.PROTOCOL_VERSION}（Python 标准库，无依赖）",
        epilog="例：python3 serve.py tests/world-arrakis --port 8000",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", type=Path, default=Path("."),
                    help="世界仓库目录（默认当前目录）")
    ap.add_argument("--host", default="127.0.0.1", help="默认只监听本机")
    ap.add_argument("--port", type=int, default=8000, help="0 = 随便挑一个空端口")
    ap.add_argument("--pack", action="append", default=[], choices=["econ"],
                    help="启用协议扩展包（econ = WGP-econ 数值系统，CA6xx）")
    ap.add_argument("--quiet", action="store_true", help="不打每行请求日志")
    a = ap.parse_args(argv)

    root = a.root.resolve()
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2

    packs, extra_known = canonlint._load_packs(a.pack)
    if packs is None:
        print("error: 扩展包 econ 不可用（econ.py 应与 canonlint.py 同目录）", file=sys.stderr)
        return 2

    serve(root, a.host, a.port, packs, extra_known, a.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
