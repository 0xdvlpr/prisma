// Prisma AI server: a small proxy between the Prisma site and the Claude API.
// The API key stays here (a Cloudflare secret), never in the browser.
// Guards: only Prisma's own site, a fixed model, capped length, a per-visitor hourly limit
// and only Prisma's own tool. Set a monthly spend limit in the Anthropic Console as the hard cap.

const MAX_BODY = 64_000;      // bytes of request JSON
const MAX_MESSAGES = 14;
const MAX_TOKENS = 1200;
const TOOL_NAMES = new Set(["find_stories"]);
const hits = new Map();       // best-effort per-visitor counter (per server instance)

function cors(origin, env) {
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  const ok = allowed.includes(origin) || (env.ALLOW_LOCALHOST === "1" && /^http:\/\/localhost(:\d+)?$/.test(origin));
  return {
    ok,
    headers: {
      "Access-Control-Allow-Origin": ok ? origin : allowed[0] || "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "content-type",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    },
  };
}

function json(data, status, headers) {
  return new Response(JSON.stringify(data), { status, headers: { ...headers, "content-type": "application/json" } });
}

function limited(ip, env) {
  const per = Number(env.PER_HOUR || 40);
  const hour = Math.floor(Date.now() / 3_600_000);
  const key = ip + ":" + hour;
  const n = (hits.get(key) || 0) + 1;
  hits.set(key, n);
  if (hits.size > 5000) for (const k of hits.keys()) if (!k.endsWith(":" + hour)) hits.delete(k);
  return n > per;
}

function clean(body) {
  if (!body || !Array.isArray(body.messages) || !body.messages.length || body.messages.length > MAX_MESSAGES) return null;
  const messages = body.messages.filter((m) => m && (m.role === "user" || m.role === "assistant") && m.content !== undefined);
  if (!messages.length || messages[0].role !== "user") return null;
  const out = { messages };
  if (Array.isArray(body.tools) && body.tools.length) {
    const tools = body.tools.filter((t) => t && TOOL_NAMES.has(t.name)).map((t) => ({
      name: t.name,
      description: String(t.description || "").slice(0, 1000),
      input_schema: t.input_schema && typeof t.input_schema === "object" ? t.input_schema : { type: "object", properties: {} },
    }));
    if (tools.length) out.tools = tools;
  }
  return out;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const c = cors(origin, env);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: c.headers });
    if (url.pathname === "/health") return json({ ok: true, model: env.MODEL, key: !!env.ANTHROPIC_API_KEY }, 200, c.headers);
    if (url.pathname !== "/messages" || request.method !== "POST") return json({ error: "not_found" }, 404, c.headers);
    if (!c.ok) return json({ error: "origin_not_allowed" }, 403, c.headers);
    if (!env.ANTHROPIC_API_KEY) return json({ error: "not_configured" }, 503, c.headers);

    const ip = request.headers.get("CF-Connecting-IP") || "anon";
    if (limited(ip, env)) return json({ error: "rate_limited" }, 429, c.headers);

    const raw = await request.text();
    if (raw.length > MAX_BODY) return json({ error: "too_large" }, 413, c.headers);
    let body;
    try { body = clean(JSON.parse(raw)); } catch { body = null; }
    if (!body) return json({ error: "bad_request" }, 400, c.headers);

    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({ model: env.MODEL || "claude-haiku-5-5", max_tokens: MAX_TOKENS, ...body }),
    });
    if (r.status === 429 || r.status === 529) return json({ error: "rate_limited" }, 429, c.headers);
    if (!r.ok) {
      console.log("anthropic error", r.status, (await r.text()).slice(0, 500));
      return json({ error: "upstream" }, 502, c.headers);
    }
    const data = await r.json();
    return json({ content: data.content, stop_reason: data.stop_reason }, 200, c.headers);
  },
};
