/* Service worker приложения «Планы»: офлайн-режим.
   Версию кэша меняем при каждом обновлении index.html. */
const CACHE = 'plans-v3-2026-11-23a';

const ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-512-maskable.png',
  './memes/ru-den-2-diety-koty.webp',
  './memes/ru-hulahup.webp',
  './memes/ru-kot-shashlyk.webp',
  './memes/ru-lift-lestnica.webp',
  './memes/ru-ne-segodnya.webp',
  './memes/ru-nochnaya-sosiska.webp',
  './memes/ru-otmechayu-pohudenie.webp',
  './memes/ru-pravda-o-racione.webp',
  './memes/ru-tort-mozhno.webp',
  './memes/ru-vesy-koty.webp',
  './memes/ru-voda-s-limonom.webp',
  './memes/ru2-demony-hotdog.jpg',
  './memes/ru2-dorozhka-kot.jpg',
  './memes/ru2-eda-doma-kot.jpg',
  './memes/ru2-ischezaet-zhelanie.jpg',
  './memes/ru2-kefir-vilkoy.jpg',
  './memes/ru2-mama-zovyot.jpg',
  './memes/ru2-ne-v-mom-vkuse.jpg',
  './memes/ru2-ostalos-7.jpg',
  './memes/ru2-ptichki-dieta.jpg',
  './memes/ru2-strannyy-son.jpg'
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
