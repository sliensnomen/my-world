/*!
 * wgp-client.js — WGP 数据集的小解析器（给前端用）
 *
 * 它只做四件事：
 *   ① 校验并补默认值（缺字段、坏文件、重名，都在这里收拾干净）
 *   ② 建索引（按 id、按边的进/出）
 *   ③ 给出「一个条目 + 它的关系」（脑子里那张思维导图的原料）
 *   ④ 标出指不到人的边
 *
 * 没有依赖。浏览器里 <script src="wgp-client.js">，Node 里 require/import 都行。
 * 用法：
 *     const world = await WGP.load("/api/world");
 *     const mm    = world.mindmap("bene-gesserit");   // 思维导图要的形状
 *     world.entries; world.neighbors("arrakis"); world.search("香料");
 *
 * 规矩（跟后端说好的）：关系名原样用，不翻译、不判断对错；
 * 字段名是合同，别自己加语义。
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.WGP = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var VERSION = "1";

  /* ---------------------------------------------------------------- 校验 */

  function assertData(data) {
    if (!data || typeof data !== "object") throw new Error("WGP: 数据不是对象");
    ["entries", "relations"].forEach(function (k) {
      if (!Array.isArray(data[k])) throw new Error("WGP: 数据里缺少数组 " + k);
    });
    return data;
  }

  /* ------------------------------------------------------------ 建一个世界 */

  function fromJson(data) {
    assertData(data);

    var byId = {}, byPath = {}, duplicates = [];

    var entries = (data.entries || []).map(function (raw) {
      var e = shallow(raw);
      e.broken = !!e.parse_error;                     // 读不出来的文件也要显示
      e.load_bearing = e.load_bearing === true;       // 缺字段 = false，别留 undefined
      e.ai_assisted = e.ai_assisted === true;
      e.id = (typeof e.id === "string" && e.id) ? e.id : null;
      e.title = e.title || e.id || e.path || "(没有名字)";
      e.type = e.type || "unknown";
      e.status = e.status || null;
      e.layer = e.layer || null;
      e.x_fields = e.x_fields || {};
      e.body_excerpt = e.body_excerpt || "";
      e.relations = Array.isArray(e.relations) ? e.relations : [];

      if (e.path) byPath[e.path] = e;
      if (e.id) {
        if (byId[e.id]) { e.duplicate = true; duplicates.push(e.id); }
        else byId[e.id] = e;
      }
      return e;
    });

    // 声明的悬空边（后端算好的），拿来给下面标原因用
    var danglingNote = {};
    (data.dangling || []).forEach(function (d) {
      danglingNote[d.source + "\u0000" + d.type + "\u0000" + d.target] = d.reason;
    });

    var bySource = {}, byType = {};
    var relations = (data.relations || []).map(function (raw) {
      var r = shallow({ source: null, type: "unknown", target: null }, raw);
      r.dangling = !!(r.target && !byId[r.target]);
      if (r.dangling) {
        r.danglingReason = danglingNote[r.source + "\u0000" + r.type + "\u0000" + r.target]
          || (/^[A-Za-z0-9_-]+:/.test(r.target) ? "world-ref" : "missing-id");
      }
      (bySource[r.source] = bySource[r.source] || []).push(r);
      (byType[r.type] = byType[r.type] || []).push(r);
      return r;
    });

    var byTarget = {};
    relations.forEach(function (r) {
      (byTarget[r.target] = byTarget[r.target] || []).push(r);
    });

    var world = {
      version: VERSION,
      raw: data,
      protocolVersion: data.protocol_version || null,   // 显示在页面角落就行
      contractVersion: data.contract_version || null,
      counts: data.counts || {},
      vocabularies: data.vocabularies || {},
      findings: data.findings || [],
      reports: data.reports || [],
      assets: data.assets || [],
      entries: entries,
      relations: relations,
      byId: byId,
      byPath: byPath,
      bySource: bySource,
      byTarget: byTarget,
      byType: byType,
      dangling: relations.filter(function (r) { return r.dangling; }),
      broken: entries.filter(function (e) { return e.broken; }),   // parse_error 的条目
      duplicates: duplicates
    };

    /* 取一个条目。给 id，也可以给 path（坏文件没有 id）。 */
    world.entry = function (key) {
      return byId[key] || byPath[key] || null;
    };

    /* 一个条目的全部关系：出去的 + 进来的。
     * 每一项：{ edge, type, direction: "out"|"in", other, otherEntry, dangling } */
    world.neighbors = function (id) {
      var out = (bySource[id] || []).map(function (r) {
        return { edge: r, type: r.type, direction: "out", other: r.target,
                 otherEntry: byId[r.target] || null, dangling: r.dangling };
      });
      var into = (byTarget[id] || []).map(function (r) {
        return { edge: r, type: r.type, direction: "in", other: r.source,
                 otherEntry: byId[r.source] || null, dangling: r.dangling };
      });
      return out.concat(into).sort(sortNeighbor);
    };

    /* 思维导图要的形状：中心 + 按关系名分好的枝条。
     * { center, branches: [{ type, items: [{ id, title, type, load_bearing,
     *                                        dangling, direction, other }] }] } */
    world.mindmap = function (id) {
      var center = byId[id] || byPath[id] || null;
      if (!center) return null;
      var groups = {};
      world.neighbors(center.id).forEach(function (n) {
        var item = {
          id: n.other,
          title: (n.otherEntry && n.otherEntry.title) || n.other,
          type: (n.otherEntry && n.otherEntry.type) || "unknown",
          load_bearing: !!(n.otherEntry && n.otherEntry.load_bearing),
          direction: n.direction,
          dangling: n.dangling
        };
        (groups[n.type] = groups[n.type] || []).push(item);
      });
      var branches = Object.keys(groups).sort().map(function (type) {
        return { type: type, items: groups[type].sort(sortItem) };
      });
      return { center: center, branches: branches };
    };

    /* 简单搜索：id / 标题 / 正文摘要，大小写不敏感 */
    world.search = function (q) {
      var s = String(q || "").trim().toLowerCase();
      if (!s) return [];
      return entries.filter(function (e) {
        return (e.id || "").toLowerCase().indexOf(s) >= 0
          || (e.title || "").toLowerCase().indexOf(s) >= 0
          || (e.body_excerpt || "").toLowerCase().indexOf(s) >= 0;
      });
    };

    /* 实际用到的关系名（带计数）—— 别在前端写死这些名字 */
    world.relationTypes = function () {
      return Object.keys(world.vocabularies.relation_types || byType).sort();
    };

    return world;
  }

  /* 从地址取数据。file:// 打开时浏览器不让 fetch，那就用 WGP.fromJson(嵌入的数据)。 */
  function load(url) {
    if (typeof fetch !== "function") {
      return Promise.reject(new Error("WGP: 这个环境没有 fetch，请用 WGP.fromJson(数据)"));
    }
    return fetch(url).then(function (res) {
      if (!res.ok) throw new Error("WGP: 取数据失败 " + res.status + " " + url);
      return res.json();
    }).then(fromJson);
  }

  /* ------------------------------------------------------------- 小工具 */

  function shallow(a, b) {           // Object.assign 的兼容写法
    var out = {}, k;
    for (k in a) if (Object.prototype.hasOwnProperty.call(a, k)) out[k] = a[k];
    if (b) for (k in b) if (Object.prototype.hasOwnProperty.call(b, k)) out[k] = b[k];
    return out;
  }
  function sortNeighbor(a, b) {
    return (a.type + "\u0000" + a.other).localeCompare(b.type + "\u0000" + b.other);
  }
  function sortItem(a, b) {
    return (a.title + "\u0000" + a.id).localeCompare(b.title + "\u0000" + b.id);
  }

  return { version: VERSION, fromJson: fromJson, load: load };
});
