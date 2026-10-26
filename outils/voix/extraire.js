const {chromium}=require('playwright-core');const fs=require('fs');
(async()=>{
  const b=await chromium.launch();const p=await b.newPage();
  await p.addInitScript(()=>{localStorage.setItem('speakup-a2-v1',JSON.stringify({tested:true}))});
  await p.goto('file://'+require('path').resolve(__dirname,'../../anglais-a2/index.html'));
  const items=await p.evaluate(()=>{const o=[];const add=(v,t)=>{if(t&&t.trim())o.push([v,t])};
    HYP_STORY.forEach(d=>d.lines.forEach(l=>add('eA',l.en)));
    [0,1].forEach(j=>hypDialogs(j).forEach(d=>d.lines.forEach(l=>{const B=l.w==='B';add(B?'eB':'eA',l.en);add(B?'fB':'fA',l.fr)})));
    UNITS.forEach(u=>u.phrases.forEach(x=>{add('eA',x[0]);add('fA',x[1])}));
    HYP_GRAM.forEach(x=>{add('eA',x.en);add('fA',x.fr)});
    GLOS.forEach(x=>{add('eA',x.en);add('fA',x.fr)});
    VERBS.filter(v=>v.p&&v.fr).forEach(v=>{add('eA',v.b+'. '+v.p+'. '+v.pp+'.');add('fA',v.fr.split(' ')[0])});
    const seen=new Set();return o.filter(([v,t])=>{const k=v+'|'+t;if(seen.has(k))return false;seen.add(k);return true})});
  fs.writeFileSync('items.json',JSON.stringify(items));console.log(items.length,items.filter(x=>x[0][0]==='e').length);await b.close();
})();
