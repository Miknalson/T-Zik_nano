// Service worker : réseau d'abord (toujours la dernière version si on est en ligne), cache en secours hors ligne.
const CACHE='speakup-shell';
self.addEventListener('install',e=>{self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(self.clients.claim())});
self.addEventListener('fetch',e=>{
  const r=e.request;
  if(r.method!=='GET'||new URL(r.url).origin!==self.location.origin)return;
  e.respondWith(
    fetch(r,{cache:'no-store'}).then(res=>{
      if(res.ok){const c=res.clone();caches.open(CACHE).then(ca=>ca.put(r,c))}
      return res;
    }).catch(()=>caches.match(r,{ignoreSearch:true}))
  );
});
