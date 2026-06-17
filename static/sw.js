/* ============================================================
   MC Monitor Service Worker
   策略：Network First，失败时回退到 Cache
   ============================================================ */
const CACHE_NAME = 'mcmonitor-v1';
const STATIC_ASSETS = [
  '/',
  '/dashboard',
  '/static/style.css',
  '/static/manifest.json',
];

// Install: 预缓存静态资产
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(() => {
        // 忽略安装失败，避免阻塞
      });
    })
  );
  self.skipWaiting();
});

// Activate: 清理旧版本缓存
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Fetch: Network First，失败回退到缓存
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // 非同源或不带 same-origin 的请求直接放行
  if (url.origin !== location.origin && !request.mode === 'navigate') {
    return;
  }

  // 认证类请求不走缓存
  if (request.url.includes('/api/') || request.url.includes('/login') || request.url.includes('/admin')) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then(response => {
        // 成功时克隆并缓存
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => {
        // 网络失败，从缓存读取
        return caches.match(request).then(cached => {
          if (cached) return cached;
          // 缓存也没有则返回离线提示页面
          if (request.mode === 'navigate') {
            return caches.match('/');
          }
          return new Response('离线', { status: 503 });
        });
      })
  );
});
