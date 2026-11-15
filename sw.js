/* Сервис-воркер: приложение работает офлайн, но сама страница всегда
   берётся свежая из сети (network-first) — иначе обновления не доходят */
const CACHE = 'plans-v2';
const ASSETS = ['./', './index.html', './manifest.webmanifest', './apple-touch-icon.png', './icon-192.png', './icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  if (e.request.method !== 'GET') return;

  // страница и манифест: сначала сеть, кэш — только если сеть недоступна
  if (e.request.mode === 'navigate' || e.request.destination === 'document' || e.request.url.includes('manifest.webmanifest')) {
    e.respondWith(
      fetch(e.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return res;
        })
        .catch(() => caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || caches.match('./index.html')))
    );
    return;
  }

  // остальное (иконки и т.п.): кэш, при отсутствии — сеть
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then((hit) => {
      if (hit) return hit;
      return fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      });
    })
  );
});
