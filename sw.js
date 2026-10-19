// Service worker mínimo: permite instalar la app y abrirla sin cobertura (los datos los guarda Firestore en el dispositivo).
const CACHE = "s4f-stocks-v1";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || !/^https?:/.test(req.url) || /firestore\.googleapis|identitytoolkit|securetoken/.test(req.url)) return;
  e.respondWith(fetch(req).then(res => { const copia = res.clone(); if (res.ok || res.type === "opaque") caches.open(CACHE).then(c => c.put(req, copia)); return res; }).catch(() => caches.match(req)));
});
