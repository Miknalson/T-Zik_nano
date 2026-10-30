// Interface : réseau d’abord. Modèles vocaux volumineux : cache d’abord.
const CACHE='speakup-shell',VOICE_CACHE='speakup-voices-v1';
self.addEventListener('install',e=>{self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(self.clients.claim())});
self.addEventListener('fetch',e=>{
  const r=e.request,url=new URL(r.url);
  if(r.method!=='GET'||url.origin!==self.location.origin)return;
  // Versions immuables du moteur local. Changer VOICE_CACHE si ces fichiers changent.
  if(/\/audio\/runtime\/.*\.(onnx|wasm|data)$/.test(url.pathname)||/\/audio\/([a-f0-9]{8}|silence-1)\.mp3$/.test(url.pathname)){
    e.respondWith((async()=>{
      let cache;
      try{cache=await caches.open(VOICE_CACHE);const hit=await cache.match(r);if(hit)return hit}catch(error){}
      const res=await fetch(r);
      if(res.ok&&cache)e.waitUntil(cache.put(r,res.clone()).catch(()=>{}));
      return res;
    })());return;
  }
  e.respondWith(
    fetch(r,{cache:'no-store'}).then(res=>{
      if(res.ok){const c=res.clone();e.waitUntil(caches.open(CACHE).then(ca=>ca.put(r,c)).catch(()=>{}))}
      return res;
    }).catch(()=>caches.match(r,{ignoreSearch:true}))
  );
});
