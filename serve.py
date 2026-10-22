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
from urllib.parse import quote, unquote, urlparse

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


def _header_value(value: str, *, as_path: bool = False) -> str:
    """把要放进响应头的字符串变回 ASCII。

    HTTP 头字段是 latin-1（RFC 9110 的 field-value 更窄：不许裸 CR/LF）。文件名是
    UTF-8 的，直接塞进去 `send_header` 会抛 UnicodeEncodeError —— 异常发生在已经写了
    状态行之后，于是客户端收到 **0 字节**，看起来像「接口挂了」。带 CR/LF 的文件名
    更糟：那是响应头注入。所以：路径类按百分号编码（可逆，前端 decodeURIComponent
    就能还原），其它值一律剔除 CR/LF 与控制字符。
    """
    if as_path:
        return quote(value, safe="/")
    return "".join(ch for ch in value
                   if ch >= " " and ch != "\x7f" and ord(ch) < 0x100)


class Handler(BaseHTTPRequestHandler):
    server_version = "wgp-serve/" + canonlint.PROTOCOL_VERSION
    protocol_version = "HTTP/1.1"

    # ---- 基础设施 -------------------------------------------------------

    def log_message(self, fmt, *args):  # 默认那行日志太吵，压成一行
        if not getattr(self.server, "quiet", False):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        if code == 405:
            self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v if k != "X-WGP-Path" else _header_value(v, as_path=True))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        # backslashreplace 是最后一道保险：任何漏出去的代理字符都变成 `\udcff` 字面量，
        # 而不是让整个响应变成 0 字节（`export_world` 已经清洗过一层）。
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8", "backslashreplace")
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
                "writable": bool(getattr(self.server, "wgp_writable", False)),
                "required_legs": {k: list(v)
                                  for k, v in canonlint.ledger.REQUIRED_LEGS.items()},
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
        self._json(405, {"code": "read_only", "error": "只读接口：只能用 GET/HEAD",
                         "allow": "GET, HEAD, OPTIONS", "routes": ROUTES})

    def do_POST(self):  # noqa: N802
        """写端点（人机交互 Phase 2）：只有 `--writable` 才开；默认只读。

        纪律与 pre-commit 钩子同源：先走 store 的写入路径，再跑审计——
        有 error 就回滚刚写的文件并回 422（钩子语义延伸到 HTTP）。
        """
        if not getattr(self.server, "wgp_writable", False):
            return self._readonly()
        path = unquote(urlparse(self.path).path)
        if path == "/api/entry":
            return self._post_card(event=False)
        if path == "/api/event":
            return self._post_card(event=True)
        if path == "/api/status":
            return self._post_status()
        return self._json(404, {"error": f"没有这个路由: {path}", "routes": ROUTES})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError) as e:
            return None, self._json(400, {"error": f"JSON 解析失败: {e}"})
        if not isinstance(data, dict):
            return None, self._json(400, {"error": "请求体必须是 JSON 对象"})
        return data, None

    def _post_status(self):
        """治理动作（人机交互 Phase 3）：升格（draft→trial→canon）/ 降级（archived）。

        与写卡同一条纪律：走 store 的行级写入 + 写完即审、红则回滚。
        """
        data, err = self._read_json()
        if err:
            return err
        root = self.server.wgp_root
        entry_id = data.get("id")
        updates: dict = {}
        if "status" in data:
            if data["status"] not in canonlint.VALID_STATUS:
                return self._json(400, {
                    "error": f"status={data['status']!r} 非法，须为 "
                             f"{sorted(canonlint.VALID_STATUS)}"})
            updates["status"] = data["status"]
        if "superseded_by" in data:
            updates["superseded_by"] = data["superseded_by"]
        if not entry_id or not updates:
            return self._json(400, {"error": "必须给 id 与至少一个字段（status/superseded_by）"})
        _all, index, _issues = canonlint.store.collect(root)
        target = index.get(entry_id)
        if target is None:
            return self._json(404, {"error": f"条目 `{entry_id}` 不存在"})
        old_bytes = target.path.read_bytes()
        rc, msg = canonlint.store.set_fields(root, entry_id, updates)
        if rc != 0:
            return self._json(400, {"error": msg})
        _all, _idx, findings, _reports = canonlint.run(root, 0.85, [])
        errors = [f for f in findings if f.level == "error"]
        if errors:
            target.path.write_bytes(old_bytes)
            return self._json(422, {
                "error": "审计不通过，已回滚",
                "findings": [{"rule": f.rule, "level": f.level,
                              "entry": f.entry, "message": f.message}
                             for f in errors]})
        return self._json(200, {"ok": True, "id": entry_id, "updates": updates})

    def _post_card(self, event: bool):
        root = self.server.wgp_root
        data, err = self._read_json()
        if err:
            return err
        legs = ("when", "when_sort", "by", "to", "object", "from", "result",
                "owns", "custody_of", "member_of")
        if event:
            kind = data.get("event_kind")
            if kind not in canonlint.ledger.EVENT_KINDS:
                return self._json(400, {
                    "error": f"event_kind={kind!r} 非法，须为 "
                             f"{sorted(canonlint.ledger.EVENT_KINDS)}"})
            type_ = "event"
            title = data.get("title") or f"{kind} 事件"
            fields = {k: data[k] for k in legs if k in data}
            fields["event_kind"] = kind
        else:
            type_ = data.get("type")
            title = data.get("title")
            if not type_ or not title:
                return self._json(400, {"error": "写卡必须给 type 与 title"})
            fields = {k: data[k] for k in legs + ("event_kind",) if k in data}
        before = set(root.rglob("*.md"))
        rc = canonlint.store.cmd_new(root, type_, title, data.get("id"),
                                     author=data.get("author"),
                                     fields=fields,
                                     layer_choices=canonlint.LAYERS)
        if rc == 1:
            return self._json(409, {"error": f"id `{data.get('id')}` 已存在"})
        if rc != 0:
            return self._json(400, {"error": "参数非法（type/id 缺失或不合法）"})
        _all, _idx, findings, _reports = canonlint.run(root, 0.85, [])
        errors = [f for f in findings if f.level == "error"]
        if errors:
            for p in set(root.rglob("*.md")) - before:
                p.unlink()
            return self._json(422, {
                "error": "审计不通过，已回滚",
                "findings": [{"rule": f.rule, "level": f.level,
                              "entry": f.entry, "message": f.message}
                             for f in errors]})
        return self._json(201, {"ok": True, "id": data.get("id")})

    def do_OPTIONS(self):  # noqa: N802
        # 浏览器的 CORS 预检打的就是 OPTIONS。以前没有这个方法 → 501 + HTML 错误页，
        # 预检失败，前端连 GET 都发不出去。
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_PUT = do_DELETE = do_PATCH = _readonly  # do_POST 在上面：--writable 时才开

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
        last_change = None
        try:  # 上诉窗口要有个时间锚：git 里这张卡的最后一次提交（best-effort）
            import subprocess
            p = subprocess.run(
                ["git", "log", "-1", "--format=%cI", "--", entry["path"]],
                cwd=self.server.wgp_root, capture_output=True, text=True, timeout=5)
            last_change = p.stdout.strip() or None
        except Exception:  # noqa: BLE001 —— 没有 git 或超时都不影响主数据
            last_change = None
        return self._json(200, {
            "protocol_version": data["protocol_version"],
            "contract_version": data["contract_version"],
            "entry": entry,
            "relations": edges,
            "last_change": last_change,
        })

    def _raw(self, rel: str) -> None:
        if "\x00" in rel:
            # NUL 字节会让 `Path.resolve()` 抛 ValueError，而那是未捕获的异常：连接被直接
            # 关掉，客户端拿不到任何状态码（也就分不清「没有这个文件」与「接口挂了」）。
            # 它反正不可能是世界里的文件，当「没有这个文件」回。
            return self._json(400, {"error": "路径里不能有 NUL 字节"})
        target = (self.server.wgp_root / rel.lstrip("/")).resolve()
        if not _inside(target, self.server.wgp_root) or not target.is_file():
            return self._json(404, {"error": f"世界目录里没有这个文件: {rel}"})
        # 隐藏文件与目录（.git 及其配置、钩子、索引）是工具的东西，不是世界的内容：
        # `canonlint init` 就会在世界目录里建 .git。它们照旧躺在「世界目录内」，
        # 所以只查目录穿越挡不住——这里再挡一次「路径里有没有 . 开头的段」。
        parts = target.relative_to(self.server.wgp_root).parts
        if any(part.startswith(".") for part in parts):
            return self._json(404, {
                "error": f"{rel} 是隐藏文件/目录，不属于世界内容",
                "hint": "只有世界自己的文件（条目、yaml、资产）能从这里取", })
        ctype = _CTYPES.get(target.suffix.lower(), "text/plain; charset=utf-8")
        return self._send(200, target.read_bytes(), ctype,
                          {"X-WGP-Path": str(target.relative_to(self.server.wgp_root))})

    def _static(self, path: str) -> None:
        rel = path[len("/web/"):] if path.startswith("/web/") else ""
        if "\x00" in rel:
            return self._json(400, {"error": "路径里不能有 NUL 字节"})
        target = (WEB_DIR / (rel or "index.html")).resolve()
        hidden = any(part.startswith(".") for part in target.relative_to(WEB_DIR).parts) \
            if WEB_DIR.is_dir() and _inside(target, WEB_DIR) else False
        if hidden:
            # 与 /api/raw 同一条规矩：隐藏文件是工具的东西（.env 里可能有密钥），
            # 不属于世界内容。这条检查以前只装在 /api/raw 上，/web 直接 200。
            return self._json(404, {"error": f"web/ 里没有这个文件: {rel}",
                                    "hint": "隐藏文件不对外提供"})
        if not WEB_DIR.is_dir() or not _inside(target, WEB_DIR) or not target.is_file():
            return self._json(404, {
                "error": f"web/ 里没有这个文件: {rel or 'index.html'}",
                "hint": "把前端文件放进仓库根的 web/（与 serve.py 同级）就能用同源地址打开：/web/index.html",
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
<p>世界：<code>{self.server.wgp_root.name}</code>（目录本身不对外显示）</p>
<p>{c['entries']} 个条目（{c['unparsed']} 个读不出来）｜{c['relations']} 条边（{c['dangling']} 条指不到人）｜
{c['errors']} 错误 / {c['warnings']} 警告</p>
<p>协议 <code>{data['protocol_version']}</code>，数据合同 <code>{data['contract_version']}</code></p>
<table>{rows}</table>
<p>这不是界面 —— 界面由前端写。前端文件放进仓库根的 <code>web/</code>（与 <code>serve.py</code> 同级），然后用
<code>/web/index.html</code> 打开，和接口同源。</p>
</html>
""".encode("utf-8")
        return self._send(200, html, "text/html; charset=utf-8")


def make_server(root: Path, host: str, port: int, packs=(), extra_known=frozenset(),
                quiet: bool = False, writable: bool = False) -> ThreadingHTTPServer:
    """起一个 server（不阻塞）。端口给 0 = 让系统随便挑一个空端口。"""
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.wgp_root = root.resolve()            # type: ignore[attr-defined]
    httpd.wgp_packs = tuple(packs)             # type: ignore[attr-defined]
    httpd.wgp_extra_known = extra_known        # type: ignore[attr-defined]
    httpd.quiet = quiet                        # type: ignore[attr-defined]
    httpd.wgp_writable = writable              # type: ignore[attr-defined]
    httpd.daemon_threads = True
    return httpd


def serve(root: Path, host: str, port: int, packs=(), extra_known=frozenset(),
          quiet: bool = False, writable: bool = False) -> None:
    httpd = make_server(root, host, port, packs, extra_known, quiet, writable)
    real_port = httpd.server_address[1]
    shown = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    # flush=True：`--port 0` 常被管道/子进程用来读端口，缓冲着就等于没打印
    mode = "读写接口（--writable）" if writable else "只读接口"
    print(f"WGP {mode}就绪：http://{shown}:{real_port}/api/world", flush=True)
    print(f"监听：{host}:{real_port}"
          + ("（所有网卡）" if shown != host else ""), flush=True)
    print(f"世界目录：{httpd.wgp_root}（改了 Markdown 刷新页面就是新数据）", flush=True)
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
    ap.add_argument("--writable", action="store_true",
                    help="开写端点（POST /api/entry、/api/event；写完即审，红则回滚）")
    a = ap.parse_args(argv)

    root = a.root.resolve()
    if not root.is_dir():
        print(f"error: {root} 不是目录", file=sys.stderr)
        return 2

    packs, extra_known = canonlint._load_packs(a.pack)
    if packs is None:
        print("error: 扩展包 econ 不可用（econ.py 应与 canonlint.py 同目录）", file=sys.stderr)
        return 2

    serve(root, a.host, a.port, packs, extra_known, a.quiet, a.writable)
    return 0


if __name__ == "__main__":
    sys.exit(main())
