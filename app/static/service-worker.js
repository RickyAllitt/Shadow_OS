// Shadow OS Service Worker: offline fallback + Web Push

const CACHE = 'shadow-os-v1';
const OFFLINE_URL = '/offline';
const PRECACHE = [OFFLINE_URL, '/static/icons/icon-192.png'];

self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

// Pages always come from the network (game state must be live); if that fails, show the offline page.
self.addEventListener('fetch', event => {
    if (event.request.mode !== 'navigate') return;
    event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
});

self.addEventListener('push', function (event) {
    if (event.data) {
        try {
            const data = event.data.json();

            const options = {
                body: data.message,
                icon: '/static/icons/icon-192.png',
                badge: '/static/icons/badge-72.png',
                vibrate: [300, 100, 300, 100, 300], // Tripe distinct vibration for mobile
                requireInteraction: true, // Crucial for mobile: keep in tray until interacted
                data: {
                    url: data.url || '/'
                }
            };

            event.waitUntil(
                self.registration.showNotification(data.title || 'SYSTEM ALERT', options)
            );
        } catch (e) {
            console.error('Error parsing push data', e);
            // Fallback for raw text push
            event.waitUntil(
                self.registration.showNotification('SYSTEM LOG', {
                    body: event.data.text()
                })
            );
        }
    }
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            const urlToOpen = new URL(event.notification.data.url, self.location.origin).href;

            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if (client.url === urlToOpen && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});
