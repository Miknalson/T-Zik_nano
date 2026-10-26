import json,wave,io,subprocess,os,sys
from piper import PiperVoice, SynthesisConfig
P=os.environ.get('PIPER_DIR','piper/');OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../anglais-a2/audio/')
os.makedirs(OUT,exist_ok=True)
M={'w':('en-us-lessac-medium.onnx',1.3),'eA':('en-us-lessac-medium.onnx',1.15),'eB':('en-us-ryan-high.onnx',1.15),'f':('fr-siwis-medium.onnx',1.0)}
V={k:PiperVoice.load(P+f) for k,(f,_) in M.items()}
def h(s):
    x=0x811c9dc5;b=s.encode('utf-16-le')
    for i in range(0,len(b),2):
        x^=b[i]|(b[i+1]<<8);x=(x*0x01000193)&0xffffffff
    return format(x,'08x')
items=json.load(open('items.json'));done=[]
W,I=int(sys.argv[1]),int(sys.argv[2])
for n,(v,t) in enumerate(items):
    k='f' if v[0]=='f' else v;name=h(k+'|'+t)
    if n%W!=I:done.append(name);continue
    f=OUT+name+'.mp3'
    if not os.path.exists(f):
        buf=io.BytesIO()
        with wave.open(buf,'wb') as w: V[k].synthesize_wav(t,w,syn_config=SynthesisConfig(length_scale=M[k][1]))
        subprocess.run(['ffmpeg','-y','-v','error','-f','wav','-i','-','-ac','1','-ar','22050','-b:a','40k','-f','mp3',f+'.tmp'],input=buf.getvalue(),check=True);os.rename(f+'.tmp',f)
    done.append(name)
    if n%100==0:print(n,flush=True)
if I==0: json.dump(sorted(set(done)),open(OUT+'index.json','w'),separators=(',',':'))
print('DONE',len(set(done)))
