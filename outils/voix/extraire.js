const {chromium}=require('playwright-core');const fs=require('fs');
(async()=>{
  const b=await chromium.launch(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']}:{});const p=await b.newPage();
  await p.addInitScript(()=>{localStorage.setItem('speakup-a2-v1',JSON.stringify({tested:true}))});
  await p.goto(process.env.APP_URL||'file://'+require('path').resolve(__dirname,'../../anglais-a2/index.html'));
  const items=await p.evaluate(()=>{const o=[];const add=(v,t)=>{if(t&&t.trim())o.push([v,t])};
    HYP_STORY.forEach(d=>d.lines.forEach(l=>add('eA',l.en)));
    [0,1].forEach(j=>hypDialogs(j).forEach(d=>d.lines.forEach(l=>{const B=l.w==='B';add(B?'eB':'eA',l.en);add(B?'fB':'fA',l.fr)})));
    UNITS.forEach(u=>u.phrases.forEach(x=>{add('eA',x[0]);add('fA',x[1])}));
    HYP_GRAM.forEach(x=>{add('eA',x.en);add('fA',x.fr)});
    GLOS.forEach(x=>{add('eA',x.en);add('fA',x.fr)});
    VERBS.filter(v=>v.p&&v.fr).forEach(v=>{add('eA',v.b+'. '+v.p+'. '+v.pp+'.');add('fA',v.fr.split(' ')[0])});
    // Reste de l'appli (Emma, cours, scènes, TOEIC, test…) : toutes les chaînes anglaises des données, voix eA.
    const FR=/[éèêëàâçùûîïôœ«»]|\b(le|la|les|des|une|est|sont|pour|avec|vous|nous|je|et|du|au|aux|ou|pas|que|qui|dans|sur|mot|phrase|réponse|exemple)\b/i;
    const isEn=t=>typeof t==='string'&&/^[A-Za-z0-9 ,.'’?!:;()\-$%€£/&"]+$/.test(t.trim())&&/[a-z]/.test(t)&&!/___|<|=>|\bhttps?:/.test(t)&&!FR.test(t)&&t.trim().length<220&&!/^[a-z]{0,2}[0-9]*$/i.test(t.trim());
    const walk=(x,d)=>{if(d>8||x==null)return;if(typeof x==='string'){if(isEn(x))add('eA',x.trim());return}if(Array.isArray(x)){x.forEach(y=>walk(y,d+1));return}if(typeof x==='object')Object.values(x).forEach(y=>walk(y,d+1))};
    [UNITS,BASICS,SCENES,PRON,PLB,ORAL,TOEIC_D,TOEIC_J].forEach(x=>{try{walk(x,0)}catch(e){}});
    // Textes effectivement lus : pas de détection heuristique de la langue ici.
    UNITS.forEach(u=>{(u.dialogue||[]).forEach(l=>add('eA',l.en));(u.talk||[]).forEach(([q])=>add('eA',q))});
    BASICS.forEach(l=>l.w.forEach(w=>{add('eA',w.en);add('eA',w.s)}));
    ['Very good!','Well done!','Try again!'].forEach(t=>add('eA',t));
    PRON.forEach(d=>d.pairs.flat().forEach(t=>add('eA',t)));
    [TOEIC_D,TOEIC_J].forEach(bank=>Object.entries(bank).forEach(([id,rows])=>rows.forEach(r=>{
      const q=tqMake(id,r);if(q.aud==='opts')q.o.forEach(t=>add('eA',t));else if(q.aud)add('eA',q.aud);
    })));
    VERBS.forEach(v=>{const f=enForms(v);add('eA',f.b+', '+f.past+', '+f.pp)});
    [['eA','Hello, the budget is on track.'],['eB','Great, thank you for the update.'],['fA','Bonjour, le budget est respecté.'],['fB','Parfait, merci pour le point.']].forEach(([v,t])=>add(v,t));
    // mots isolés pour le « mot à mot » : tous les mots anglais ci-dessus + formes de la conjugaison
    const W=new Set();o.filter(x=>x[0][0]==='e').forEach(([v,t])=>t.split(/\s+/).forEach(w=>{w=hypNorm(w);if(w)W.add(w)}));
    VERBS.forEach(v=>{const f=enForms(v);[f.b,f.s3,f.ing,f.past,f.pp].forEach(w=>w&&W.add(hypNorm(w)))});
    ['I','you','he','she','it','we','they','am','is','are','was','were','will','would','have','has','had','been','being','going','to','do','does','did','not'].concat(Object.values(CONTR)).forEach(w=>W.add(hypNorm(w)));
    W.forEach(w=>w&&o.push(['w',w]));
    const seen=new Set();return o.filter(([v,t])=>{const k=v+'|'+t;if(seen.has(k))return false;seen.add(k);return true})});
  fs.writeFileSync(process.env.ITEMS_PATH||'items.json',JSON.stringify(items));console.log(items.length,items.filter(x=>x[0][0]==='e').length);await b.close();
})();
