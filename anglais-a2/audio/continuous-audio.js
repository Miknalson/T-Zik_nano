/* Assemble les MP3 enregistrés en un seul média : aucune minuterie JS n’est
   nécessaire entre les mots ou les phrases quand iOS suspend la page. */
const ContinuousAudio=(()=>{
  const files=new Map();
  function parse(buffer){
    const bytes=new Uint8Array(buffer),frames=[];let pos=0,format=null;
    if(String.fromCharCode(...bytes.slice(0,3))==='ID3'){
      pos=10+((bytes[6]&127)<<21)+((bytes[7]&127)<<14)+((bytes[8]&127)<<7)+(bytes[9]&127);
      if(bytes[5]&16)pos+=10;
    }
    while(pos+4<=bytes.length){
      const b=bytes[pos+1],c=bytes[pos+2],d=bytes[pos+3];
      if(bytes[pos]!==255||(b&224)!==224){pos++;continue}
      const version=(b>>3)&3,layer=(b>>1)&3,index=c>>4,sr=(c>>2)&3;
      if(version===1||layer!==1||index===0||index===15||sr===3){pos++;continue}
      const rate=[44100,48000,32000][sr]/(version===3?1:version===2?2:4);
      const bitrate=(version===3?[0,32,40,48,56,64,80,96,112,128,160,192,224,256,320]:[0,8,16,24,32,40,48,56,64,80,96,112,128,144,160])[index]*1000;
      const samples=version===3?1152:576,size=Math.floor((version===3?144:72)*bitrate/rate)+((c>>1)&1);
      if(pos+size>bytes.length)break;
      const signature=[version,rate,bitrate,d>>6].join('/');
      const frame=bytes.subarray(pos,pos+size);
      // Supprimer les anciennes durées Xing/Info et les balises ID3 de chaque clip.
      const tag=String.fromCharCode(...frame.slice(4,80));
      if(!(frames.length===0&&/Xing|Info/.test(tag))){
        if(format&&format!==signature)throw Error('Formats MP3 incompatibles');
        format=signature;frames.push({start:pos,end:pos+size,seconds:samples/rate});
      }
      pos+=size;
    }
    if(!frames.length)throw Error('MP3 vide ou illisible');
    return {bytes,frames,format,seconds:frames.reduce((n,f)=>n+f.seconds,0)};
  }
  async function file(key){
    if(files.has(key))return files.get(key);
    const pending=fetch(new URL(key,document.baseURI)).then(r=>{
      if(!r.ok)throw Error('Audio absent : '+key);return r.arrayBuffer();
    }).then(parse).catch(e=>{files.delete(key);throw e});
    files.set(key,pending);return pending;
  }
  async function prepare(segments,{seconds,rate=1,current=()=>true,progress=()=>{}}){
    if(!segments.length)throw Error('Aucune lecture à préparer');
    const keys=[...new Set(segments.filter(s=>s.key).map(s=>s.key).concat('audio/silence-1.mp3'))];
    let next=0,completed=0;
    await Promise.all(Array.from({length:Math.min(6,keys.length)},async()=>{
      while(next<keys.length){if(!current())throw Error('cancelled');await file(keys[next++]);progress(++completed,keys.length)}
    }));
    if(!current())throw Error('cancelled');
    const silence=await file('audio/silence-1.mp3'),parts=[],chapters=[];
    let limit=seconds==null?0:seconds*rate;
    if(seconds==null){for(const s of segments)limit+=s.key?(await file(s.key)).seconds:s.silence*rate}
    let elapsed=0,cycle=0,format=null;
    function append(clip,maxSeconds){
      if(format&&clip.format!==format)throw Error('Formats MP3 incompatibles');format=clip.format;
      const first=clip.frames[0];let last=null,time=0;
      for(const f of clip.frames){if(time+f.seconds>maxSeconds)break;last=f;time+=f.seconds}
      if(last){parts.push(clip.bytes.subarray(first.start,last.end));elapsed+=time}
      return time;
    }
    while(limit-elapsed>=silence.frames[0].seconds){
      for(const s of segments){
        if(!current())throw Error('cancelled');
        if(limit-elapsed<silence.frames[0].seconds)break;
        if(s.meta)chapters.push({time:elapsed,cycle,...s.meta});
        if(s.key)append(await file(s.key),limit-elapsed);
        else{
          let gap=Math.min(s.silence*rate,limit-elapsed);
          while(gap>=silence.frames[0].seconds){const added=append(silence,gap);if(!added)break;gap-=added}
        }
      }
      cycle++;if(seconds==null)break;
    }
    if(!parts.length)throw Error('Séance vide');
    return {blob:new Blob(parts,{type:'audio/mpeg'}),chapters,seconds:elapsed,rate};
  }
  return {parse,prepare};
})();
