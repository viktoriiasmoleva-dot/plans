/* Service worker приложения «Планы»: офлайн-режим.
   Версию кэша меняем при каждом обновлении index.html. */
const CACHE = 'plans-v3-2026-11-28m';

const ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-512-maskable.png',
  './memes/ru3-dieta-1.jpg',
  './memes/ru3-dieta-2.jpg',
  './memes/ru3-dieta-3.jpg',
  './memes/ru3-dieta-4.jpg',
  './memes/ru3-dieta-5.jpg',
  './memes/ru3-dieta-6.jpg',
  './memes/ru3-dieta-7.jpg',
  './memes/ru3-dieta-8.jpg',
  './memes/ru3-dieta-9.jpg',
  './memes/ru3-dieta-10.jpg',
  './memes/ru3-dieta-11.jpg',
  './memes/ru3-dieta-12.jpg',
  './memes/ru3-dieta-13.jpg'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      /* каждый файл кладём отдельно: один недоступный не ломает весь офлайн */
      .then((cache) => Promise.all(ASSETS.map((u) => cache.add(u).catch(() => null))))
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
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  /* страницы: сначала сеть (чтобы обновления прилетали), при ошибке — из кэша */
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req)
        .then((resp) => {
          if (resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put('./index.html', copy));
            return resp;
          }
          return caches.match('./index.html');
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  /* ресурсы: сначала кэш, потом сеть */
  e.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((resp) => {
        if (resp && resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return resp;
        }
        return cached || resp;
      });
    })
  );
});
