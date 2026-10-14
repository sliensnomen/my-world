#!/usr/bin/env node
/* 解析器 wgp-client.js 的行为测试（在 node 下跑）。
 *
 *   node tests/test_client_js.js world.json bad.json crash.json
 *
 * 三个参数都是 canonlint export 的真实输出：正常世界、有悬空边的世界、有坏文件的世界。
 */
"use strict";
const fs = require("fs");
const path = require("path");
const WGP = require(path.join(__dirname, "..", "wgp-client.js"));

const [arrakisFile, badFile, crashFile] = process.argv.slice(2);
let failed = 0;

function check(label, fn) {
  try {
    fn();
    console.log("PASS " + label);
  } catch (e) {
    failed += 1;
    console.log("FAIL " + label + "：" + e.message);
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}
function load(file) {
  return WGP.fromJson(JSON.parse(fs.readFileSync(file, "utf8")));
}
function assertThrows(fn, msg) {
  let threw = false;
  try { fn(); } catch (e) { threw = true; }
  assert(threw, msg);
}

const world = load(arrakisFile);

check("条目数与 counts 对得上", function () {
  assert(world.entries.length === world.counts.entries,
    "entries=" + world.entries.length + " counts=" + world.counts.entries);
});

check("缺字段被补上（title 非空、load_bearing 是布尔）", function () {
  world.entries.forEach(function (e) {
    assert(typeof e.title === "string" && e.title.length > 0, "title 空: " + e.path);
    assert(typeof e.load_bearing === "boolean", "load_bearing 不是布尔: " + e.path);
    assert(typeof e.relations === "object", "relations 不是数组: " + e.path);
  });
});

check("byId 取得到条目、entry() 给 id 和 path 都能取", function () {
  const e = world.entry("bene-gesserit");
  assert(e && e.type === "faction", "取不到 bene-gesserit");
  const byPath = world.entry("entries/bene-gesserit.md");
  assert(byPath && byPath.id === "bene-gesserit", "按 path 取不到");
});

check("neighbors 两个方向都给", function () {
  const arrakis = world.neighbors("arrakis");
  assert(arrakis.length > 0, "arrakis 一条关系都没有？");
  assert(arrakis.some(function (n) { return n.direction === "in"; }), "没有进边");
  arrakis.forEach(function (n) {
    assert(n.type && n.other, "关系缺 type/other");
  });
});

check("mindmap 是「中心 + 按关系名分的枝条」", function () {
  const mm = world.mindmap("bene-gesserit");
  assert(mm && mm.center.id === "bene-gesserit", "中心不对");
  assert(mm.branches.length > 0, "没有枝条");
  mm.branches.forEach(function (b) {
    assert(typeof b.type === "string" && b.type, "枝条没有名字");
    assert(Array.isArray(b.items) && b.items.length > 0, "空枝条 " + b.type);
  });
});

check("mindmap 对不存在的 id 返回 null（不抛）", function () {
  assert(world.mindmap("没有这个条目") === null, "应该返回 null");
});

check("relationTypes 与 vocabularies 一致", function () {
  const names = world.relationTypes();
  assert(names.length > 0, "关系名为空");
  names.forEach(function (n) {
    assert(world.vocabularies.relation_types[n] > 0, n + " 计数为 0");
  });
});

check("search 找得到（大小写不敏感、能给空结果）", function () {
  assert(world.search("ARRAKIS").length > 0, "搜不到 ARRAKIS");
  assert(world.search("").length === 0, "空串应该给空数组");
});

check("两次解析结果一致（没有随机/时间戳）", function () {
  const a = JSON.stringify(load(arrakisFile).mindmap("bene-gesserit"));
  const b = JSON.stringify(load(arrakisFile).mindmap("bene-gesserit"));
  assert(a === b, "两次结果不一样");
});

check("数据不是对象时直接报错", function () {
  assertThrows(function () { WGP.fromJson(null); }, "null 应该报错");
  assertThrows(function () { WGP.fromJson({ entries: [] }); }, "缺 relations 应该报错");
});

if (badFile) {
  const bad = load(badFile);
  check("悬空边被标出来（含世界外引用）", function () {
    assert(bad.dangling.length === bad.counts.dangling,
      "标出 " + bad.dangling.length + " 条，counts 说 " + bad.counts.dangling + " 条");
    assert(bad.dangling.some(function (r) { return r.danglingReason === "world-ref"; }),
      "没认出 world-ref");
    assert(bad.dangling.some(function (r) { return r.danglingReason === "missing-id"; }),
      "没认出 missing-id");
  });
}

if (crashFile) {
  const crash = load(crashFile);
  check("坏文件也进列表（有 path、无 id、可显示）", function () {
    assert(crash.broken.length === 1, "坏文件数=" + crash.broken.length);
    const b = crash.broken[0];
    assert(b.id === null, "坏文件不该有 id");
    assert(b.parse_error, "没有 parse_error 说明");
    assert(crash.entry(b.path) === b, "坏文件应该能按 path 取到");
  });
}

console.log(failed ? "FAILED " + failed : "OK");
process.exit(failed ? 1 : 0);
