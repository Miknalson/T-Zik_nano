import * as ort from 'onnxruntime-web/wasm';
import createPhonemizer from '@diffusionstudio/piper-wasm/build/piper_phonemize.js';

// Un thread : compatible avec un site statique sans COOP/COEP, dont GitHub Pages.
ort.env.wasm.numThreads=1;
ort.env.wasm.wasmPaths=new URL('./',self.location.href).href;
let session=null,language=null,config=null,queue=Promise.resolve();
const cancelled=new Set();
async function fetchFile(name,json=false){
  const r=await fetch(new URL(name,self.location.href));
  if(!r.ok)throw Error('Fichier vocal indisponible : '+name);
  return json?r.json():r.arrayBuffer();
}
async function loadVoice(lang){
  if(session&&language===lang)return;
  if(session)await session.release();
  session=null;language=null;
  const [model,metadata]=await Promise.all([fetchFile('models/'+lang+'.onnx'),fetchFile('models/'+lang+'.onnx.json',true)]);
  session=await ort.InferenceSession.create(model,{executionProviders:['wasm']});
  config=metadata;language=lang;
}
async function phonemeIds(text){
  let result;
  const module=await createPhonemizer({
    print:data=>{result=JSON.parse(data)},
    locateFile:name=>new URL(name,self.location.href).href
  });
  module.callMain(['-l',config.espeak.voice,'--input',JSON.stringify([{text}]),'--espeak_data','/espeak-ng-data']);
  if(!Array.isArray(result?.phonemes))throw Error('Conversion phonétique impossible');
  // Les modèles historiques ont leur propre table, différente de celle du WASM.
  const map=config.phoneme_id_map,ids=[...map['^'],...map['_']];
  for(const phoneme of result.phonemes)if(map[phoneme])ids.push(...map[phoneme],...map['_']);
  ids.push(...map['$']);return ids;
}
function chunks(text){
  const parts=[];let current='';
  for(const word of text.trim().split(/\s+/)){
    if(current.length+word.length>320){parts.push(current);current=''}
    current+=(current?' ':'')+word;
    if(/[.!?]$/.test(word)&&current.length>180){parts.push(current);current=''}
  }
  if(current)parts.push(current);return parts;
}
function wave(pcms){
  const count=pcms.reduce((n,p)=>n+p.length,0),buffer=new ArrayBuffer(44+count*2),v=new DataView(buffer);
  const str=(offset,s)=>{for(let i=0;i<s.length;i++)v.setUint8(offset+i,s.charCodeAt(i))};
  str(0,'RIFF');v.setUint32(4,buffer.byteLength-8,true);str(8,'WAVEfmt ');v.setUint32(16,16,true);
  v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,config.audio.sample_rate,true);
  v.setUint32(28,config.audio.sample_rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);
  str(36,'data');v.setUint32(40,count*2,true);let offset=44;
  for(const pcm of pcms)for(const sample of pcm){v.setInt16(offset,Math.max(-1,Math.min(1,sample))*32767,true);offset+=2}
  return new Blob([buffer],{type:'audio/wav'});
}
async function synthesize(text,id){
  const pcms=[];
  for(const part of chunks(text)){
    if(cancelled.has(id))return null;
    const ids=await phonemeIds(part);
    const feeds={
      input:new ort.Tensor('int64',BigInt64Array.from(ids,BigInt),[1,ids.length]),
      input_lengths:new ort.Tensor('int64',BigInt64Array.from([ids.length],BigInt),[1]),
      scales:new ort.Tensor('float32',Float32Array.from([config.inference.noise_scale,language==='en'?1.15:1,config.inference.noise_w]),[3])
    };
    if(config.num_speakers>1)feeds.sid=new ort.Tensor('int64',BigInt64Array.from([0],BigInt),[1]);
    const result=await session.run(feeds);
    pcms.push(new Float32Array(result.output.data));
    for(const tensor of Object.values(result))tensor.dispose();
    for(const tensor of Object.values(feeds))tensor.dispose();
  }
  return wave(pcms);
}
self.onmessage=({data})=>{
  if(data.cancel){cancelled.add(data.cancel);return}
  queue=queue.then(async()=>{
    const {id,text,lang}=data;
    try{
      if(cancelled.has(id))return;
      const next=lang.startsWith('fr')?'fr':'en';
      if(language!==next)self.postMessage({id,status:'loading'});
      await loadVoice(next);
      if(cancelled.has(id))return;
      self.postMessage({id,status:'synthesizing'});
      const blob=await synthesize(text,id);
      if(blob&&!cancelled.has(id))self.postMessage({id,blob});
    }catch(error){self.postMessage({id,error:String(error.message||error)})}
    finally{cancelled.delete(id)}
  });
};
