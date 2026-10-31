/* Prisma public-site adapter.
   On claude.ai the app talks to window.claude. Here we provide the same calls:
   - db: reads the daily edition.json
   - sample: Claude via the Prisma AI server (worker/), if config.json names one
   - downloads: saves files with a normal browser download */
(function () {
  if (window.claude) return;
  window.PRISMA_PUBLIC = true;

  var ed = fetch("edition.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  var cfg = fetch("config.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; });

  function snap(rows) { return { docs: rows.map(function (r) { return { id: r[0], exists: true, data: function () { return r[1]; } }; }) }; }
  var db = {
    doc: function (p) {
      return { get: async function () {
        var e = await ed;
        return p === "meta/edition" && e && e.updated_at ? { exists: true, data: function () { return { updatedAt: e.updated_at }; } } : { exists: false, data: function () { return null; } };
      } };
    },
    collection: function (n) {
      return { onSnapshot: function (ok) {
        ed.then(function (e) {
          if (n === "editions" && e && e.countries) ok(snap(e.countries.filter(function (c) { return c.stories && c.stories.length; }).map(function (c) { return [c.code.toLowerCase(), { stories: c.stories }]; })));
          else ok(snap([]));
        });
        return function () {};
      } };
    }
  };

  var downloads = { save: async function (o) {
    var u = URL.createObjectURL(o.data), a = document.createElement("a");
    a.href = u; a.download = o.filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(u); }, 4000);
  } };

  /* ---------- AI ---------- */
  function fail(code, text) { var e = new Error(code); e.code = code; if (text) e.text = text; return e; }
  async function call(base, body) {
    var r;
    try { r = await fetch(base.replace(/\/$/, "") + "/messages", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }); }
    catch (e) { throw fail("network"); }
    if (r.status === 429) throw fail("rate_limited");
    if (!r.ok) throw fail("server");
    return r.json();
  }
  function textOf(msg) { return (msg.content || []).filter(function (b) { return b.type === "text"; }).map(function (b) { return b.text; }).join(""); }
  function parseJSON(t) {
    t = String(t || "").replace(/^```(?:json)?\s*|\s*```$/g, "");
    try { return JSON.parse(t); } catch (e) {}
    var a = t.indexOf("{"), b = t.lastIndexOf("}");
    if (a >= 0 && b > a) { try { return JSON.parse(t.slice(a, b + 1)); } catch (e) {} }
    throw fail("bad_json");
  }
  function makeSample(base) {
    async function sample(input, opts) {
      opts = opts || {};
      var messages = typeof input === "string" ? [{ role: "user", content: input }] : input.map(function (m) { return { role: m.role, content: m.content }; });
      var tools = opts.tools || [];
      var spec = tools.map(function (t) { return { name: t.name, description: t.description, input_schema: t.inputSchema || { type: "object", properties: {} } }; });
      var text = "";
      for (var turn = 0; turn < 5; turn++) {
        var res = await call(base, { messages: messages, tools: spec.length ? spec : undefined });
        text = textOf(res);
        if (opts.onText && text) opts.onText({ text: text });
        var uses = (res.content || []).filter(function (b) { return b.type === "tool_use"; });
        if (res.stop_reason !== "tool_use" || !uses.length) return { text: text };
        messages = messages.concat([{ role: "assistant", content: res.content }]);
        var results = [];
        for (var i = 0; i < uses.length; i++) {
          var t = tools.find(function (x) { return x.name === uses[i].name; }), out;
          try { out = t ? await t.execute(uses[i].input || {}) : { error: "Unknown tool" }; } catch (e) { out = { error: "Tool failed" }; }
          results.push({ type: "tool_result", tool_use_id: uses[i].id, content: JSON.stringify(out) });
        }
        messages = messages.concat([{ role: "user", content: results }]);
      }
      return { text: text };
    }
    sample.json = async function (prompt) {
      var res = await call(base, { messages: [{ role: "user", content: prompt + "\n\nReply with the JSON only, no other text." }] });
      return parseJSON(textOf(res));
    };
    return sample;
  }

  window.claude = { use: async function (n) {
    if (n === "db") return db;
    if (n === "downloads") return downloads;
    if (n === "sample") { var c = await cfg; return c && c.ai ? makeSample(c.ai) : null; }
    return null;
  } };

  /* ---------- offline + install ---------- */
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
    addEventListener("load", function () { navigator.serviceWorker.register("sw.js").catch(function () {}); });
  }
})();
