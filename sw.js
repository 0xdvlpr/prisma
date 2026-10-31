/* Prisma service worker: opens instantly, works offline with the last edition. */
const VERSION = "prisma-v2";
const SHELL = ["./", "index.html", "public.js", "edition.json", "manifest.webmanifest", "icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "vendor/d3-7.8.5.min.js", "vendor/topojson-3.0.2.min.js"];

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(VERSION);
    await c.addAll(SHELL);
    self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== VERSION) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function networkFirst(req) {
  const c = await caches.open(VERSION);
  try {
    const r = await fetch(req, { cache: "no-cache" });
    if (r.ok) c.put(req, r.clone());
    return r;
  } catch (e) {
    const hit = await c.match(req, { ignoreSearch: true });
    if (hit) return hit;
    if (req.mode === "navigate") return c.match("index.html");
    throw e;
  }
}

async function staleWhileRevalidate(req) {
  const c = await caches.open(VERSION);
  const hit = await c.match(req);
  const fresh = fetch(req).then((r) => { if (r.ok || r.type === "opaque") c.put(req, r.clone()); return r; }).catch(() => hit);
  return hit || fresh;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    // The page and today's edition: always try for the newest, fall back to the saved copy.
    if (req.mode === "navigate" || /\/(edition|config)\.json$/.test(url.pathname) || /\/index\.html$/.test(url.pathname)) {
      e.respondWith(networkFirst(req));
      return;
    }
    e.respondWith(staleWhileRevalidate(req));
    return;
  }
  if (url.hostname.endsWith("fonts.googleapis.com") || url.hostname.endsWith("fonts.gstatic.com")) {
    e.respondWith(staleWhileRevalidate(req));
  }
});
