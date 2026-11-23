'use strict';
const worker = /** @type {ServiceWorkerGlobalScope} */ (/** @type {unknown} */ (self));
const CACHE = 'pivot-shell-v113-basketball-context';
const SHELL = ['/', '/index.html', '/app.css', '/app.js', '/mvp.js', '/mvp.css', '/experience.css', '/refresh.css', '/experience.js', '/catalog.css', '/catalog-demos.js', '/catalog.js', '/workout.css', '/workout.js', '/assets/court.jpg', '/assets/strength.png', '/mark.svg', '/icon-192.png', '/icon-512.png', '/manifest.webmanifest'];
worker.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => worker.skipWaiting())); });
worker.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('pivot-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => worker.clients.claim())); });
worker.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== worker.location.origin || event.request.method !== 'GET' || url.search) return;
  // Keep application responses and media out of the offline shell.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/media/')) return;
  if (!SHELL.includes(url.pathname)) return;
  event.respondWith(fetch(event.request).then(async response => {
    if (response.status === 200 && !response.redirected) {
      try {
        const cache = await caches.open(CACHE);
        await cache.put(event.request, response.clone());
      } catch {
        // A cache write failure must not hide a usable network response.
      }
    }
    return response;
  }).catch(() => caches.match(event.request, { cacheName: CACHE })
    .then(cached => cached || new Response('应用界面尚未缓存，请联网后重新打开。', {
      status: 503,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
    }))));
});
