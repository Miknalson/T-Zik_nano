/* Voix Piper locales pour les textes absents des MP3 (conjugaison, tuteur, dictionnaire).
   Les modèles sont chargés seulement à la première phrase générée dans chaque langue. */
const naturalWorkerURL=new URL('runtime/worker.js',document.currentScript.src);
const naturalOutput=new Audio();let naturalUnlocked=false,naturalPlayback=0;
function naturalUnlock(){
  if(naturalUnlocked||(naturalOutput.src&&!naturalOutput.src.startsWith('data:')))return;
  const silent='data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';naturalOutput.src=silent;
  naturalOutput.play().then(()=>{naturalUnlocked=true;if(naturalOutput.src===silent)naturalOutput.pause()}).catch(()=>{});
}
addEventListener('touchend',naturalUnlock,{passive:true});addEventListener('click',naturalUnlock);
let naturalWorker=null,naturalId=0,naturalFailureShown=false;
const naturalJobs=new Map(),naturalCache=new Map(),naturalLanguages=new Set();
function naturalFail(){
  if(!naturalFailureShown){naturalFailureShown=true;toast('Voix naturelle indisponible : la voix de l’appareil prend le relais.',5000)}
}
function naturalEngine(){
  if(naturalWorker)return naturalWorker;
  const worker=naturalWorker=new Worker(naturalWorkerURL,{type:'module'});
  worker.onmessage=({data})=>{
    const job=naturalJobs.get(data.id);if(!job)return;
    if(data.status==='loading'&&!naturalLanguages.has(job.lang)){
      naturalLanguages.add(job.lang);toast('Préparation de la voix naturelle… Le premier chargement peut prendre un moment.',6000);
    }
    if(data.blob||data.error){naturalJobs.delete(data.id);data.error?job.reject(Error(data.error)):job.resolve(data.blob)}
  };
  worker.onerror=()=>{
    worker.terminate();naturalWorker=null;
    for(const job of naturalJobs.values())job.reject(Error('Moteur vocal indisponible'));
    naturalJobs.clear();
  };
  return worker;
}
async function naturalSpeak(text,lang,rate,token){
  if(!text?.trim())return true;
  const key=lang+'|'+text;
  let audio=null,url=null,timer=null,run=0;
  const current=()=>token===spk;
  const stopped={};
  try{
    let blob=naturalCache.get(key);
    if(!blob){
      const id=++naturalId,worker=naturalEngine();
      blob=await new Promise((resolve,reject)=>{
        const cancel=setInterval(()=>{
          if(!current()){clearInterval(cancel);clearTimeout(timeout);naturalJobs.delete(id);worker.postMessage({cancel:id});reject(stopped)}
        },100);
        const timeout=setTimeout(()=>{
          clearInterval(cancel);naturalJobs.delete(id);reject(Error('Délai de synthèse dépassé'));
          // Une inférence bloquée ne doit pas bloquer les lectures suivantes.
          worker.terminate();if(naturalWorker===worker)naturalWorker=null;
          for(const job of naturalJobs.values())job.reject(Error('Moteur vocal redémarré'));
          naturalJobs.clear();
        },180000);
        const finish=fn=>value=>{clearInterval(cancel);clearTimeout(timeout);fn(value)};
        naturalJobs.set(id,{lang,resolve:finish(resolve),reject:finish(reject)});
        worker.postMessage({id,text,lang});
      });
      naturalCache.set(key,blob);
      if(naturalCache.size>24)naturalCache.delete(naturalCache.keys().next().value);
    }
    if(!current())return true;
    run=++naturalPlayback;url=URL.createObjectURL(blob);audio=naturalOutput;audio.src=url;audio.preservesPitch=true;audio.webkitPreservesPitch=true;
    audio.playbackRate=hypPR(rate);
    await new Promise((resolve,reject)=>{
      timer=setInterval(()=>{if(!current()||run!==naturalPlayback){if(run===naturalPlayback)audio.pause();resolve()}},100);
      audio.onended=resolve;audio.onerror=reject;audio.play().catch(reject);
    });
    return true;
  }catch(error){
    if(error===stopped||!current())return true;
    naturalFail();return false;
  }finally{
    clearInterval(timer);
    if(audio&&run===naturalPlayback){audio.onended=audio.onerror=null;audio.pause()}
    if(url)URL.revokeObjectURL(url);
  }
}

// Même élément audio déverrouillé par le toucher pour les MP3 et les voix générées.
function recordedSpeak(url,rate,maxMs,token,fallback){
  const audio=naturalOutput,run=++naturalPlayback;
  return new Promise(resolve=>{
    let finished=false,watchdog,check;
    const owns=()=>run===naturalPlayback;
    const done=ok=>{
      if(finished)return;finished=true;clearInterval(check);clearTimeout(watchdog);
      const active=owns();
      if(active){audio.onended=audio.onerror=null;if(!ok)audio.pause()}
      if(!ok&&active&&token===spk){try{Promise.resolve(fallback()).then(resolve,resolve)}catch(e){resolve()}}
      else resolve();
    };
    check=setInterval(()=>{if(token!==spk||!owns()){if(owns())audio.pause();done(true)}},100);
    watchdog=setTimeout(()=>done(false),maxMs);
    audio.onended=()=>done(true);audio.onerror=()=>done(false);
    audio.src=url;audio.preservesPitch=true;audio.webkitPreservesPitch=true;audio.playbackRate=hypPR(rate);
    try{audio.play().catch(()=>done(false))}catch(e){done(false)}
  });
}
