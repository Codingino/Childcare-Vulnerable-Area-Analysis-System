'use strict';
const CACHE='ieum-shell-v2.0.0';
const SHELL=['/','/app.js','/style.css','/icon.svg','/icon-192.png','/icon-512.png','/manifest.webmanifest','/evidence.json'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('ieum-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;if(!SHELL.includes(url.pathname))return;event.respondWith(fetch(event.request).then(response=>{if(response.ok){const clone=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(url.pathname,clone)));}return response;}).catch(()=>caches.match(url.pathname).then(cached=>cached||new Response('오프라인에서 불러올 수 없습니다.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}}))));});
