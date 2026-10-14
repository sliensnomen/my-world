#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口（serve.py）与解析器（wgp-client.js）的边界测试。

跑法：python3 tests/test_serve.py

检查的东西：接口给的数据必须和 CLI 导出**一模一样**（两份实现会漂，这一条钉死）；
坏文件的世界不能把接口弄崩；悬空边要报出来；只读；不能穿越目录；没 node 就跳过 JS 那项（跳过会明说）。
"""
from __future__ import annotations

import json
import re
import shutil
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


def server_for(world: Path) -> str:
    """每个世界起一个接口（端口让系统随便挑），复用。"""
    key = str(world)
    if key not in _SERVERS:
        httpd = serve.make_server(world, "127.0.0.1", 0, quiet=True)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _SERVERS[key] = f"http://127.0.0.1:{httpd.server_address[1]}"
    return _SERVERS[key]


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
    assert d["counts"]["dangling"] == len(d["dangling"]) == 2, \
        f"悬空边数={d['counts']['dangling']}/{len(d['dangling'])}"
    reasons = sorted(x["reason"] for x in d["dangling"])
    assert reasons == ["missing-id", "world-ref"], f"原因不对：{reasons}"
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
    for bad in ("/api/raw/../../../../etc/passwd",
                "/api/raw/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
                "/api/raw/../canonlint.py"):
        status, _, _ = get(server_for(WORLD) + bad)
        assert status == 404, f"{bad} 应该 404，实际 {status}"


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
    """一份样例必须和真实导出逐字段对得上——干净版和带注释版都要过这一关。"""
    assert set(sample) == set(real), (
        f"{where} 顶层键 {sorted(sample)} 与真实导出 {sorted(real)} 不一致")
    assert sample["protocol_version"] == canonlint.PROTOCOL_VERSION, (
        f"{where} 的 protocol_version={sample['protocol_version']}，代码是 {canonlint.PROTOCOL_VERSION}")
    assert sample["contract_version"] == canonlint.CONTRACT_VERSION, (
        f"{where} 的 contract_version={sample['contract_version']}，代码是 {canonlint.CONTRACT_VERSION}")
    assert sample["entries"], f"{where} 里一个条目都没有"
    want, got = set(real["entries"][0]), set(sample["entries"][0])
    assert got == want, (
        f"{where} 的条目键与真实导出不一致：多了 {sorted(got - want)}，少了 {sorted(want - got)}")
    assert sample["relations"], f"{where} 里一条边都没有"
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


CHECKS = [
    ("接口给的数据 = CLI 导出的数据", check_world_同_CLI_导出),
    ("两次请求一致，且不漏绝对路径", check_两次请求一致_且没有绝对路径),
    ("单个条目接口（含进边和出边）", check_单个条目接口),
    ("查不到的条目给 404 并说明", check_没这个条目给_404_且说明清楚),
    ("有坏文件的世界接口不崩", check_坏文件的世界不崩),
    ("悬空边照原样报出来（不隐藏）", check_悬空边照原样报出来),
    ("原始文件只读接口", check_原始文件接口),
    ("不能穿越出世界目录", check_不能穿越目录),
    ("只读：写方法一律 405", check_只读),
    ("响应头（CORS / 不缓存 / JSON）", check_响应头),
    ("首页说明页与 /api/health", check_首页与存活),
    ("不存在的路由给 404 并列路由", check_不存在的路由给_404),
    ("解析器 wgp-client.js 在 node 下行为正确", check_解析器在_node_下的行为),
    ("文档里写的路由都真实存在", check_文档写的路由都是真的),
    ("文档里的 JSON 样例与真实导出一致", check_文档里的_JSON_样例与真实导出一致),
    ("字段说明覆盖真实导出的每个字段", check_字段说明覆盖真实导出的每个字段),
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
    tail = f"{len(CHECKS)} 项检查 | {len(CHECKS) - failed - skipped} 通过"
    if skipped:
        tail += f" | {skipped} 跳过"
    tail += f" | {failed} 失败" if failed else " | 全部通过"
    print("\n" + tail)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
