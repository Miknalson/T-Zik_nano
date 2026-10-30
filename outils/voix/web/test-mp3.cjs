const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../../anglais-a2');
const context=vm.createContext({Blob});
vm.runInContext(fs.readFileSync(path.join(root,'audio/continuous-audio.js'),'utf8')+';globalThis.parse=ContinuousAudio.parse',context);
const keys=JSON.parse(fs.readFileSync(path.join(root,'audio/index.json'),'utf8'));
let format;
for(const name of keys.concat('silence-1')){
  const bytes=fs.readFileSync(path.join(root,'audio',name+'.mp3'));
  const parsed=context.parse(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
  assert(parsed.frames.length>0&&parsed.seconds>0);
  format??=parsed.format;
  assert.equal(parsed.format,format,'Les clips assemblés doivent partager le même format');
}
assert.throws(()=>context.parse(new ArrayBuffer(10)),/MP3 vide/);
console.log('OK : '+keys.length+' enregistrements et silence compatibles avec la piste continue.');
