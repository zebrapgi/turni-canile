// Service Worker per le Notifiche Push del Canile
self.addEventListener('push', function(event) {
  const data = event.data ? event.data.json() : { title: 'Canile', body: 'Nuovo aggiornamento turni' };
  
  const options = {
    body: data.body,
    icon: 'https://cdn-icons-png.flaticon.com/512/616/616408.png',
    badge: 'https://cdn-icons-png.flaticon.com/512/616/616408.png',
    vibrate: [200, 100, 200]
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.openWindow('/')
  );
});
