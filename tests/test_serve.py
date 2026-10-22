#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口（serve.py）与解析器（wgp-client.js）的边界测试。

跑法：python3 tests/test_serve.py

检查的东西：接口给的数据必须和 CLI 导出**一模一样**（两份实现会漂，这一条钉死）；
坏文件的世界不能把接口弄崩；悬空边要报出来；只读；不能穿越目录；没 node 就跳过 JS 那项（跳过会明说）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import canonlint  # noqa: E402
import serve  # noqa: E402

WORLD = ROOT / "tests" / "world-arrakis"      # 22 个条目、24 条边、没有坏文件
BAD = ROOT / "tests" / "world-bad"            # 有 2 条悬空边
CRASH = ROOT / "tests" / "world-crash"        # 有 1 个读不出来的文件

_SERVERS: dict = {}


def server_for(world: Path, writable: bool = False) -> str:
    """每个世界起一个接口（端口让系统随便挑），复用。"""
    key = f"{world}::w{int(writable)}"
    if key not in _SERVERS:
        httpd = serve.make_server(world, "127.0.0.1", 0, quiet=True,
                                  writable=writable)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _SERVERS[key] = f"http://127.0.0.1:{httpd.server_address[1]}"
    return _SERVERS[key]


def post(url: str, payload: dict):
    """POST 一个 JSON 对象，返回 (status, body, headers)。"""
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.status, res.read(), dict(res.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def get(url: str, method: str = "GET"):
    # 路径里可能有中文 id，先按规矩转义——接口那头会自己解回来
    p = urllib.parse.urlsplit(url)
    safe = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path),
                                   p.query, p.fragment))
    req = urllib.request.Request(safe, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.status, res.read(), dict(res.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)



def raw_get(base: str, path: str) -> tuple[int, bytes]:
    """不经 urllib 的请求：路径原样发出去。

    `get()` 会 `urllib.parse.quote` 一遍，`%2e` 被二次转义成 `%252e`，于是「编码穿越」
    这类用例其实从来没走到守卫跟前（评审 3.3）。裸 socket 才能把原始字节发出去。
    """
    u = urllib.parse.urlsplit(base)
    req = f"GET {path} HTTP/1.1\r\nHost: {u.hostname}\r\nConnection: close\r\n\r\n"
    with socket.create_connection((u.hostname, u.port), timeout=20) as sock:
        sock.sendall(req.encode("latin-1"))
        chunks = []
        while True:
            b = sock.recv(65536)
            if not b:
                break
            chunks.append(b)
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    assert head, f"{path!r}：连接被直接关掉，没有返回任何响应头"
    return int(head.split(b" ")[1]), body

def world_json(world: Path = WORLD) -> dict:
    return json.loads(get(server_for(world) + "/api/world")[1])


# --------------------------------------------------------------- 检查项

def check_world_同_CLI_导出() -> None:
    api = world_json()
    direct = canonlint.export_world(WORLD)
    assert api == direct, "接口给的数据和 `canonlint export` 的不一致（两份实现漂了）"


def check_两次请求一致_且没有绝对路径() -> None:
    a = get(server_for(WORLD) + "/api/world")[1]
    b = get(server_for(WORLD) + "/api/world")[1]
    assert a == b, "同一份数据两次请求字节不一样（有随机或时间戳？）"
    assert b"/home/" not in a, "接口把主机上的绝对路径漏出去了"
    assert str(ROOT).encode() not in a, "接口把仓库根目录漏出去了"


def check_单个条目接口() -> None:
    status, body, _ = get(server_for(WORLD) + "/api/entry/bene-gesserit")
    assert status == 200, f"状态码 {status}"
    d = json.loads(body)
    full = world_json()
    assert d["entry"] == next(e for e in full["entries"] if e["id"] == "bene-gesserit"), \
        "单条接口给的条目和整份数据里的不一样"
    want = [r for r in full["relations"]
            if r["source"] == "bene-gesserit" or r["target"] == "bene-gesserit"]
    assert d["relations"] == want, "单条接口漏了边（进边或出边）"


def check_没这个条目给_404_且说明清楚() -> None:
    status, body, _ = get(server_for(WORLD) + "/api/entry/没有这个条目")
    assert status == 404, f"应该 404，实际 {status}"
    msg = json.loads(body)["error"]
    assert "没有这个条目" in msg, f"报错文案不对：{msg}"


def check_坏文件的世界不崩() -> None:
    d = world_json(CRASH)
    assert d["counts"]["unparsed"] == 1, f"坏文件数={d['counts']['unparsed']}"
    broken = [e for e in d["entries"] if e.get("parse_error")]
    assert len(broken) == 1, "没有把坏文件当成条目给出来"
    b = broken[0]
    assert b["id"] is None and b["path"] == "entries/bad-utf8.md", f"坏文件条目不对：{b['path']}"
    assert b["body_chars"] == 0 and b["relations"] == [], "坏文件不该有正文或关系"
    status, _, _ = get(server_for(CRASH) + "/api/entry/entries/bad-utf8.md")
    assert status == 404, "坏文件没有 id，按 id 查就该 404"


def check_悬空边照原样报出来() -> None:
    d = world_json(BAD)
    assert d["counts"]["dangling"] == len(d["dangling"]) == 3, \
        f"悬空边数={d['counts']['dangling']}/{len(d['dangling'])}"
    reasons = sorted(x["reason"] for x in d["dangling"])
    assert reasons == ["missing-id", "missing-id", "world-ref"], f"原因不对：{reasons}"
    # 其中一条来自被重复 id 遮蔽的条目：遮蔽改变的是「引用的目标指向谁」，
    # 不改变「这条引用本身写坏了」，所以它照样要出现在导出里。
    assert any(x["target"] == "ghost-nowhere" for x in d["dangling"]), \
        "被遮蔽条目里的悬空引用没被导出"
    targets = {x["target"] for x in d["dangling"]}
    assert any(t.startswith("otherworld:") for t in targets), "世界外引用没被认出来"
    edges = {(r["source"], r["type"], r["target"]) for r in d["relations"]}
    assert all((x["source"], x["type"], x["target"]) in edges for x in d["dangling"]), \
        "悬空边既要在 dangling 里，也要留在 relations 里（不能悄悄消失）"


def check_原始文件接口() -> None:
    status, body, headers = get(server_for(WORLD) + "/api/raw/entries/arrakis.md")
    assert status == 200, f"状态码 {status}"
    assert body == (WORLD / "entries" / "arrakis.md").read_bytes(), "给的不是原文件"
    assert headers.get("X-WGP-Path") == "entries/arrakis.md", "少了 X-WGP-Path"


def check_不能穿越目录() -> None:
    """穿越锁要证明「内容没被拿走」，不能只证明「状态码是 404」。

    评审指出：这条锁原来只断言 404，于是「给 404 响应回显文件前 24 字节」这种改动
    照样全绿——裸 socket 实际读出了 /etc/passwd 的 `root:x:0:0::`。名字说「不能穿越
    目录」，断言说「状态码是 404」，这是两件事。所以这里在世界**上一级**放一个标记
    文件，用裸请求打各种写法：既要 404，也要响应体里不许出现世界外的内容。
    """
    with tempfile.TemporaryDirectory() as td:
        outer = Path(td)
        world = outer / "world"
        (world / "entries").mkdir(parents=True)
        (world / "entries" / "a.md").write_text(
            "---\nid: a\ntitle: A\ntype: location\n---\n正文\n", encoding="utf-8")
        secret = "TOP-SECRET-CANARY-9f3a"
        (outer / "outside.md").write_text(secret + "\n", encoding="utf-8")
        base = server_for(world)
        attacks = [
            "/api/raw/../outside.md",
            "/api/raw/../../etc/passwd",
            "/api/raw/%2e%2e%2foutside.md",
            "/api/raw/%2E%2E%2Foutside.md",
            "/api/raw/..%2foutside.md",
            "/api/raw/%2e%2e/%2e%2e/etc/passwd",
            "/api/raw/./../outside.md",
            "/api/raw//etc/passwd",
            "/api/raw/..%5coutside.md",
        ]
        for bad in attacks:
            status, body = raw_get(base, bad)
            text = body.decode("utf-8", "replace")
            assert status == 404, f"{bad} 应该 404，实际 {status}"
            assert secret not in text, f"{bad} 的响应体里带出了世界外的内容"
            assert "root:" not in text, f"{bad} 的响应体里带出了系统文件"
        # 正面：世界自己的文件必须取得到（别把守卫收得过紧，收成「什么都 404」）
        status, body = raw_get(base, "/api/raw/entries/a.md")
        assert status == 200 and "id: a" in body.decode("utf-8"), \
            f"世界自己的文件取不到（{status}）：守卫收过头了"


def check_隐藏文件取不到() -> None:
    """世界目录里藏着工具自己的东西（`canonlint init` 会建 .git 与钩子）。

    它们在里面，所以「不许穿越出去」那条挡不住；这里要求按隐藏段挡掉——
    把 .git/config 端出去等于把工具的元数据当世界观内容发。
    """
    root = WORLD
    hidden = root / ".git"
    hidden.mkdir(exist_ok=True)
    (hidden / "config").write_text("[core]\n\trepositoryformatversion = 0\n",
                                   encoding="utf-8")
    try:
        for bad in ("/api/raw/.git/config", "/api/raw/.git/", "/api/raw/./.git/config",
                    "/api/raw/.env"):
            status, body, _ = get(server_for(WORLD) + bad)
            assert status == 404, f"{bad} 应该 404，实际 {status}"
        body = get(server_for(WORLD) + "/api/raw/.git/config")[1]
        assert b"repositoryformatversion" not in body, ".git/config 的内容被端出去了"
    finally:
        # 夹具世界是仓库里的目录，不能留下这次测试的痕迹
        (hidden / "config").unlink(missing_ok=True)
        hidden.rmdir()
    # 正常文件照旧能取
    status, _, _ = get(server_for(WORLD) + "/api/raw/entries/arrakis.md")
    assert status == 200, f"正常条目反而取不到了：{status}"



def check_路径里的_NUL_字节不是断连() -> None:
    """带 NUL 字节的请求必须给出状态码，不许把连接一关了事。

    `Path.resolve()` 遇到 NUL 抛 ValueError，以前没人接：请求方拿到的是空响应，
    分不清「没有这个文件」与「接口挂了」。它不可能是世界里的文件，按 400 回。
    """
    status, body = raw_get(server_for(WORLD), "/api/raw/entries/\x00arrakis.md")
    assert status == 400, f"NUL 字节应该 400，实际 {status}"
    assert "NUL" in json.loads(body)["error"], f"报错没说清原因：{body[:200]}"
    # 静态路由同样
    status, _ = raw_get(server_for(WORLD), "/web/\x00index.html")
    assert status in (400, 404), f"/web 的 NUL 字节应该 400/404，实际 {status}"


def check_web_静态路由不许穿越() -> None:
    """`/web/` 只许取 web/ 里的文件（评审 L1：这道守卫从来没被锁过）。

    仓库里没有 web/ 目录，所以以前根本走不到守卫。这里临时造一个，并在它**外面**
    放一个秘密文件，从两个方向试穿越：`..` 折返、以及 `..%2f` 这类编码写法。
    """
    import tempfile  # noqa: PLC0415

    old_web = serve.WEB_DIR
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        web = root / "web"
        web.mkdir()
        (web / "index.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")
        secret = root / "secret.txt"
        secret.write_text("TOP-SECRET", encoding="utf-8")
        serve.WEB_DIR = web
        try:
            base = server_for(WORLD)
            status, body = raw_get(base, "/web/index.html")
            assert status == 200 and b"ok" in body, f"正常静态文件取不到：{status}"
            for bad in ("/web/../secret.txt", "/web/..%2fsecret.txt",
                        "/web/%2e%2e/secret.txt", "/web/....//secret.txt",
                        "/web//etc/passwd"):
                status, body = raw_get(base, bad)
                assert status == 404, f"{bad} 应该 404，实际 {status}"
                assert b"TOP-SECRET" not in body, f"{bad} 把 web/ 外面的文件端出去了"
        finally:
            serve.WEB_DIR = old_web


def check_web_目录不存在时的提示() -> None:
    """没装前端时要明确说「把前端放这里就能用」，而不是一个光秃秃的 404。"""
    import tempfile  # noqa: PLC0415

    old_web = serve.WEB_DIR
    with tempfile.TemporaryDirectory() as td:
        serve.WEB_DIR = Path(td) / "不存在的目录"
        try:
            status, body, _ = get(server_for(WORLD) + "/web/index.html")
            assert status == 404, f"应该 404，实际 {status}"
            assert "web/" in json.loads(body)["hint"], f"提示没说清放哪里：{body[:200]}"
        finally:
            serve.WEB_DIR = old_web

def check_只读() -> None:
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        status, body, _ = get(server_for(WORLD) + "/api/world", method=method)
        assert status == 405, f"{method} 应该 405，实际 {status}"
        assert "只读" in json.loads(body)["error"], f"{method} 的报错没说清是只读"


def check_响应头() -> None:
    status, _, headers = get(server_for(WORLD) + "/api/world")
    assert headers.get("Access-Control-Allow-Origin") == "*", "没有 CORS 头，前端跨端口取不到"
    assert headers.get("Cache-Control") == "no-store", "不能缓存：改了 Markdown 要立刻看到"
    assert "application/json" in headers.get("Content-Type", ""), "Content-Type 不对"


def check_首页与存活() -> None:
    status, body, headers = get(server_for(WORLD) + "/")
    assert status == 200 and "text/html" in headers.get("Content-Type", ""), "首页不对"
    text = body.decode("utf-8")
    assert "只读接口" in text and "个条目" in text, "首页没给出状态"
    status, body, _ = get(server_for(WORLD) + "/api/health")
    d = json.loads(body)
    assert status == 200 and d["ok"] is True, "health 不对"
    assert d["contract_version"] == canonlint.CONTRACT_VERSION, "health 里的合同版本不对"


def check_不存在的路由给_404() -> None:
    status, body, _ = get(server_for(WORLD) + "/api/没有这个")
    assert status == 404, f"应该 404，实际 {status}"
    assert "routes" in json.loads(body), "404 里应该把可用路由列出来"


def check_解析器在_node_下的行为() -> str | None:
    node = shutil.which("node")
    if not node:
        return "没装 node"
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for world, name in ((WORLD, "world.json"), (BAD, "bad.json"), (CRASH, "crash.json")):
            p = Path(tmp) / name
            p.write_text(json.dumps(canonlint.export_world(world), ensure_ascii=False),
                         encoding="utf-8")
            paths.append(str(p))
        r = subprocess.run([node, str(ROOT / "tests" / "test_client_js.js"), *paths],
                           capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise AssertionError("解析器测试没过：\n" + (r.stdout or "")[-1200:] + (r.stderr or "")[-400:])
    return None


DOCS_FRONT = [ROOT / "docs" / "接口说明.md", ROOT / "docs" / "给前端的说明.md"]


def check_文档写的路由都是真的():
    """文档是发给别人的合同：里面写的每个 /api/… 都必须真的存在，否则对方照着写就是 404。"""
    seen, unknown = set(), []
    for doc in DOCS_FRONT:
        assert doc.exists(), f"{doc} 不见了（前端说明是交付物的一部分）"
        for token in re.findall(r"`(?:GET +)?(/(?:api|web)[^`]*)`", doc.read_text(encoding="utf-8")):
            token = token.rstrip("。，,、")
            if re.search(r"(^|/)\.\.(/|$)", token):
                continue  # 这是文档里的反例（"这样取会被拒"），不是路由
            seen.add(token)
            if token in serve.ROUTES:
                continue
            prefixes = [r[:-3] for r in serve.ROUTES if r.endswith("...")]
            if any(token.startswith(p) for p in prefixes):
                continue
            unknown.append(f"{doc.name} → {token}")
    assert not unknown, f"文档里写了不存在的路由：{unknown}"
    assert seen, "两份前端文档里一条路由都没写（路径是不是拼错了？）"
    # 反过来：接口里有的路由，文档也必须写到——不然对方不知道有这个出口
    undocumented = [r for r in serve.ROUTES if r != "/" and not any(
        r == s or (r.endswith("...") and s.startswith(r[:-3])) for s in seen)]
    assert not undocumented, f"接口里有文档没写的路由：{undocumented}"


def _strip_jsonc(text: str) -> str:
    """把 // 注释去掉（字符串里的不算），好让带注释的说明版也能被机器核对。"""
    out, i, in_string, quote = [], 0, False, ""
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\":
                out.append(text[i + 1] if i + 1 < len(text) else "")
                i += 2
                continue
            if ch == quote:
                in_string = False
            i += 1
            continue
        if ch in "\"'":
            in_string, quote = True, ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _verify_sample(sample, real, where: str):
    """一份样例必须和真实导出**逐字段、逐值**对得上——干净版和带注释版都要过这一关。

    以前这里只比**键名**：把 counts 改成 999、dangling 塞进两条压根不存在的边、
    findings 写成世界不会报的 CA301、fields 换成 `{"totally_fake": 1}`，四种改法全都
    照样通过（评审 F2 的变异实验）。文档那句话写的是「真实输出，没有手编」——那就得
    真的按值比：样例允许**截短列表**，但不许出现真实导出里没有的东西。
    """
    assert set(sample) == set(real), (
        f"{where} 顶层键 {sorted(sample)} 与真实导出 {sorted(real)} 不一致")
    assert sample["protocol_version"] == canonlint.PROTOCOL_VERSION, (
        f"{where} 的 protocol_version={sample['protocol_version']}，代码是 {canonlint.PROTOCOL_VERSION}")
    assert sample["contract_version"] == canonlint.CONTRACT_VERSION, (
        f"{where} 的 contract_version={sample['contract_version']}，代码是 {canonlint.CONTRACT_VERSION}")

    # counts 与 vocabularies 是「速览」，不是列表——必须整个相等，不许截短
    assert sample["counts"] == real["counts"], (
        f"{where} 的 counts 与真实导出不一致：\n  样例 {sample['counts']}\n  真实 {real['counts']}")
    assert sample["vocabularies"] == real["vocabularies"], (
        f"{where} 的 vocabularies 与真实导出不一致：\n  样例 {sample['vocabularies']}\n"
        f"  真实 {real['vocabularies']}")

    # 列表允许截短：样例里出现的每一项，都必须能在真实导出里**原样**找到
    for key in ("entries", "relations", "dangling", "findings", "assets", "reports"):
        assert isinstance(sample.get(key), list), f"{where} 的 {key} 不是列表"
        for item in sample[key]:
            assert item in real[key], (
                f"{where} 的 {key} 里有真实导出里不存在的项（文档在编数据）："
                f"\n  {item}\n真实导出里同类项有 {len(real[key])} 条")

    # 条目与边的「形状」也要对：真实导出会给的键，样例一条都不能少
    if sample["entries"]:
        want = set(real["entries"][0])
        got = set(sample["entries"][0])
        assert got == want, (
            f"{where} 的条目键与真实导出不一致：多了 {sorted(got - want)}，少了 {sorted(want - got)}")
    if sample["relations"]:
        rel_keys = set()
        for edge in real["relations"]:
            rel_keys |= set(edge)
        extra = set(sample["relations"][0]) - rel_keys
        assert not extra, f"{where} 的边里有真实导出不会给的键：{sorted(extra)}"


def check_文档里的_JSON_样例与真实导出一致():
    """文档里的样例是别人开工的依据：干净版和带注释版都必须与真实导出逐字段对得上。"""
    doc = ROOT / "docs" / "给前端的说明.md"
    text = doc.read_text(encoding="utf-8")
    real = canonlint.export_world(WORLD)
    # 干净版：优先找 ```json，没有就逐个试（编辑器保存时可能把语言标记抹掉）
    blocks = re.findall(r"```json\n(.*?)```", text, re.S) or re.findall(r"```\n(.*?)```", text, re.S)
    sample = None
    for block in blocks:
        try:
            sample = json.loads(block)
            break
        except ValueError:
            continue
    assert sample is not None, "给前端的说明里找不到能解析的 JSON 样例（样例就是合同的一半）"
    _verify_sample(sample, real, "干净样例")
    # 带注释的说明版：去掉 // 之后必须跟干净版说得一样（不然两份会漂）
    jsonc = re.findall(r"```jsonc\n(.*?)```", text, re.S)
    assert jsonc, "带注释的说明版不见了（它是给人看的那一份）"
    annotated = json.loads(_strip_jsonc(jsonc[0]))
    _verify_sample(annotated, real, "带注释的说明版")


def check_字段说明覆盖真实导出的每个字段():
    """第四节的字段表就是对方的字典：真实导出里有的字段，一个都不许漏（漏了只能猜）。"""
    doc = ROOT / "docs" / "给前端的说明.md"
    text = doc.read_text(encoding="utf-8")
    assert "## 四、字段是什么意思" in text, "给前端的说明里找不到「字段是什么意思」那一节"
    body = text.split("## 四、字段是什么意思", 1)[1].split("\n## ", 1)[0]
    documented = set(re.findall(r"`([a-z_]{2,})`", body))
    documented |= set(re.findall(r"([a-z_]{2,})\\\[\\\]", body))  # 形如 entries\[\] 的小标题
    real = canonlint.export_world(WORLD, impact=("arrakis",))     # 带上 report，字段才全
    fields = set(real)
    for key in ("entries", "relations", "dangling", "findings", "reports", "assets"):
        for item in real.get(key, []):
            fields |= set(item)
    fields |= set(real.get("counts", {}))
    fields |= set(real.get("vocabularies", {}))
    missing = sorted(f for f in fields if f not in documented)
    assert not missing, f"字段说明里没写到这些字段：{missing}"


def check_导出透出事件字段与派生状态():
    """B6：export 透出事件字段与 derive_state——前端要渲染「谁拿着什么」。

    冰火世界有真实流水：ice-sword 的派生持有者是 eddard-stark、保管是
    house-stark；jon-snow 的守夜人归属来自 join 流水。事件卡的六个字段
    与断言字段原样透出。
    """
    real = canonlint.export_world(ROOT / "tests" / "world-westeros")
    assert set(real["ledger"]) == {"states", "membership"}, \
        f"ledger 段的键不对：{sorted(real['ledger'])}"
    st = real["ledger"]["states"].get("ice-sword")
    assert st and st["holder"] == "eddard-stark", f"ice-sword 派生持有者不对：{st}"
    assert st["custodian"] == "house-stark", f"ice-sword 派生保管不对：{st}"
    assert real["ledger"]["membership"].get("jon-snow", {}).get("night-watch-order") == "join", \
        f"琼恩的组织归属不对：{real['ledger']['membership'].get('jon-snow')}"
    ev = next(d for d in real["entries"] if d["id"] == "ev-ice-to-ned")
    for key in ("when", "when_sort", "event_kind", "by", "to", "object"):
        assert ev[key] is not None, f"事件卡没透出 {key}：{ev}"
    assert ev["event_kind"] == "transfer"
    jon = next(d for d in real["entries"] if d["id"] == "jon-snow")
    assert jon["member_of"] == ["night-watch-order"], f"member_of 没透出：{jon}"


def check_只读界面被伺候且指向数据源():
    """web/index.html（人机交互 Phase 1）：只读界面真实存在、从 /api/world 取数。

    三个视图（台账/审计/流水）的关键字样都在；界面不引构建链（没有 <script src= 外链框架）。
    """
    page = ROOT / "web" / "index.html"
    assert page.is_file(), "web/index.html 不存在"
    text = page.read_text(encoding="utf-8")
    for marker in ("/api/world", "台账", "审计", "流水", "派生状态"):
        assert marker in text, f"web/index.html 少了 {marker!r}"
    assert "cdn" not in text and "unpkg" not in text and "jsdelivr" not in text, \
        "界面引了外链框架（约定是零依赖、零构建）"
    base = server_for(WORLD)
    code, body, _headers = get(f"{base}/web/index.html")
    assert code == 200 and "派生状态" in body.decode("utf-8"), \
        f"/web/index.html 没被正确伺候：{code}"


def check_可写模式的写入与审计回滚():
    """serve --writable（人机交互 Phase 2）：POST 写卡与记账，审计红则回滚。

    默认只读（POST 一律 405）；开了 --writable：写卡 → 出现在 /api/world；
    记账 → 悬空腿让审计变红 → 422 且刚写的文件被回滚（世界不留残骸）。
    /api/health 要告诉前端它可写、每种 event_kind 要哪些腿。
    """
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "w"
        (world / "entries").mkdir(parents=True)
        # 只读模式下 POST 依然 405
        code, body, _ = post(f"{server_for(world)}/api/event",
                             {"event_kind": "transfer"})
        assert code == 405, f"只读模式 POST 应 405，实际 {code}：{body[:200]}"
        base = server_for(world, writable=True)
        code, body, _ = get(f"{base}/api/health")
        health = json.loads(body)
        assert health["writable"] is True, f"health 没说可写：{health}"
        assert health["required_legs"]["transfer"] == ["by", "to", "object"], \
            f"required_legs 不对：{health['required_legs']}"
        # 写三张卡
        for eid, type_ in (("anna", "character"), ("bob", "character"),
                           ("sword-x", "item")):
            code, body, _ = post(f"{base}/api/entry",
                                 {"type": type_, "title": eid, "id": eid})
            assert code == 201, f"写 {eid} 失败：{code} {body[:300]}"
        # 记一笔账：腿都指向真卡 → 201，且能在 /api/world 里看到
        code, body, _ = post(f"{base}/api/event", {
            "event_kind": "transfer", "id": "ev-1", "title": "剑易手",
            "by": ["anna"], "to": ["bob"], "object": ["sword-x"],
            "when": "元年", "when_sort": 1})
        assert code == 201, f"记账失败：{code} {body[:300]}"
        data = json.loads(get(f"{base}/api/world")[1])
        ev = next((d for d in data["entries"] if d["id"] == "ev-1"), None)
        assert ev and ev["event_kind"] == "transfer", f"ev-1 没进导出：{ev}"
        # 悬空腿 → 审计红 → 422，且文件被回滚
        code, body, _ = post(f"{base}/api/event", {
            "event_kind": "transfer", "id": "ev-ghost",
            "by": ["anna"], "to": ["ghost-nobody"], "object": ["sword-x"],
            "when": "二年", "when_sort": 2})
        assert code == 422, f"悬空腿应 422，实际 {code}：{body[:300]}"
        assert not (world / "entries/events/ev-ghost.md").exists(), \
            "审计红了的卡没被回滚"
        # 坏 kind → 400
        code, body, _ = post(f"{base}/api/event", {"event_kind": "explode"})
        assert code == 400, f"坏 kind 应 400，实际 {code}"


def check_治理端点的升格降级与回滚():
    """POST /api/status（人机交互 Phase 3）：升格/降级走行级写入 + 写完即审。

    升格 draft→trial→canon 绿灯放行；降级 archived 且无承接者、仍被 canon_refs
    引用 → CA405 error → 422 且文件被回滚（治理动作不能把世界写红）。
    """
    with tempfile.TemporaryDirectory() as td:
        world = Path(td) / "w"
        (world / "entries").mkdir(parents=True)
        base = server_for(world, writable=True)
        for eid in ("old-lore", "reader-card"):
            code, body, _ = post(f"{base}/api/entry",
                                 {"type": "event", "title": eid, "id": eid})
            assert code == 201, f"写 {eid} 失败：{code} {body[:300]}"
        # reader-card 引用 old-lore（canon_refs）
        code, body, _ = post(f"{base}/api/entry",
                             {"type": "event", "title": "引用者", "id": "ref-1"})
        assert code == 201, body[:300]
        # 升格：draft → trial → canon 一路绿灯
        for st in ("trial", "canon"):
            code, body, _ = post(f"{base}/api/status",
                                 {"id": "old-lore", "status": st})
            assert code == 200, f"升格到 {st} 失败：{code} {body[:300]}"
        # 降级但还被人引用、又不给承接者 → CA405 → 422 回滚
        path = world / "entries/events/old-lore.md"
        ref_path = world / "entries/events/ref-1.md"
        ref_path.write_text(ref_path.read_text(encoding="utf-8").replace(
            "canon_refs: []", "canon_refs:\n  - old-lore"), encoding="utf-8")
        before = path.read_bytes()
        code, body, _ = post(f"{base}/api/status",
                             {"id": "old-lore", "status": "archived"})
        assert code == 422, f"无承接者的降级应 422，实际 {code}：{body[:300]}"
        assert path.read_bytes() == before, "CA405 红了的降级没被回滚"
        # 没人引用、有承接者的降级 → 放行（降级处置完整的合法形态）
        code, body, _ = post(f"{base}/api/entry",
                             {"type": "event", "title": "承接者", "id": "new-lore"})
        assert code == 201, body[:300]
        code, body, _ = post(f"{base}/api/status",
                             {"id": "reader-card", "status": "archived",
                              "superseded_by": "new-lore"})
        assert code == 200, f"无人引用 + 有承接者的降级应放行：{code} {body[:300]}"
        # 不存在的条目 → 404
        code, body, _ = post(f"{base}/api/status",
                             {"id": "ghost", "status": "trial"})
        assert code == 404, f"未知条目应 404，实际 {code}"


CHECKS = [
    ("接口给的数据 = CLI 导出的数据", check_world_同_CLI_导出),
    ("两次请求一致，且不漏绝对路径", check_两次请求一致_且没有绝对路径),
    ("单个条目接口（含进边和出边）", check_单个条目接口),
    ("查不到的条目给 404 并说明", check_没这个条目给_404_且说明清楚),
    ("有坏文件的世界接口不崩", check_坏文件的世界不崩),
    ("悬空边照原样报出来（不隐藏）", check_悬空边照原样报出来),
    ("原始文件只读接口", check_原始文件接口),
    ("不能穿越出世界目录", check_不能穿越目录),
    ("隐藏文件（.git 等）取不到", check_隐藏文件取不到),
    ("路径里的 NUL 字节给状态码，不断连", check_路径里的_NUL_字节不是断连),
    ("/web 静态路由不许穿越出 web/", check_web_静态路由不许穿越),
    ("没装前端时 /web 说清放哪里", check_web_目录不存在时的提示),
    ("只读：写方法一律 405", check_只读),
    ("响应头（CORS / 不缓存 / JSON）", check_响应头),
    ("首页说明页与 /api/health", check_首页与存活),
    ("不存在的路由给 404 并列路由", check_不存在的路由给_404),
    ("解析器 wgp-client.js 在 node 下行为正确", check_解析器在_node_下的行为),
    ("文档里写的路由都真实存在", check_文档写的路由都是真的),
    ("文档里的 JSON 样例与真实导出一致", check_文档里的_JSON_样例与真实导出一致),
    ("字段说明覆盖真实导出的每个字段", check_字段说明覆盖真实导出的每个字段),
    ("导出透出事件字段与派生状态（B6）", check_导出透出事件字段与派生状态),
    ("只读界面被伺候且指向数据源（Phase 1）", check_只读界面被伺候且指向数据源),
    ("可写模式的写入与审计回滚（Phase 2）", check_可写模式的写入与审计回滚),
    ("治理端点的升格降级与回滚（Phase 3）", check_治理端点的升格降级与回滚),
]


def main() -> int:
    failed, skipped = 0, 0
    for label, fn in CHECKS:
        try:
            note = fn()
        except AssertionError as e:
            failed += 1
            print(f"FAIL {label}\n     {e}")
        except Exception as e:  # 意料之外的错也要看见，不算通过
            failed += 1
            print(f"FAIL {label}\n     {type(e).__name__}: {e}")
        else:
            if isinstance(note, str):
                skipped += 1
                print(f"SKIP {label}（{note}）")
            else:
                print(f"PASS {label}")
    # 跳过必须是**被看见**的：CI 里没有 node 时，这一套以前是 exit 0 + 一行「1 跳过」，
    # 外部无法区分「JS 解析器检查真的跑了」和「它根本没跑」。想接受跳过就显式设
    # CANONLINT_ALLOW_SKIP=1——沉默的绿不算绿。
    skip_is_failure = bool(skipped) and os.environ.get("CANONLINT_ALLOW_SKIP") != "1"

    tail = f"{len(CHECKS)} 项检查 | {len(CHECKS) - failed - skipped} 通过"
    if skipped:
        tail += f" | {skipped} 跳过"
    if failed:
        tail += f" | {failed} 失败"
    elif skip_is_failure:
        tail += " | 未通过（跳过未获授权，设 CANONLINT_ALLOW_SKIP=1 才接受）"
    else:
        tail += " | 全部通过"
    print("\n" + tail)
    return 1 if (failed or skip_is_failure) else 0


if __name__ == "__main__":
    sys.exit(main())
