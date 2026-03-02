// Web Push Service Worker

self.addEventListener('push', function (event) {
    if (event.data) {
        try {
            const data = event.data.json();

            const options = {
                body: data.message,
                icon: '/static/icons/sys-icon-192.png', // Fallback, assuming generic icon
                badge: '/static/icons/sys-icon-192.png',
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
