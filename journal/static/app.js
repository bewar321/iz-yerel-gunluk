'use strict';
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="journal-token"]').content;
const state = {entries: [], revision: null, busy: false, formSnapshot: '', toastTimer: null, view: 'journal'};
const fields = ['title','body','event_date','kind','mood','reason','expectation','outcome','helpful_note','analyze'];
const fieldId = key => key === 'event_date' ? 'entry-date' : 'entry-'+key;
const localDay = () => { const d=new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const formatDate = (value, monthOnly=false) => new Date(value.length===7 ? value+'-01T12:00:00' : value.length===10 ? value+'T12:00:00' : value).toLocaleDateString('tr-TR', monthOnly ? {year:'numeric',month:'long'} : {day:'numeric',month:'long',year:'numeric'});
function el(tag, className, text) { const n=document.createElement(tag); if(className) n.className=className; if(text!==undefined) n.textContent=text; return n; }
function toast(text) { $('toast').textContent=text; $('toast').hidden=false; clearTimeout(state.toastTimer); state.toastTimer=setTimeout(()=>$('toast').hidden=true,5000); }
async function api(path, options={}) {
  const response=await fetch('/api/'+path,{...options,headers:{'X-Journal-Token':token,'Content-Type':'application/json',...(options.headers||{})}});
  let data; try {data=await response.json();} catch {throw new Error('Sunucudan yanıt alınamadı. Uygulamanın açık olduğundan emin ol.');}
  if(!response.ok) throw new Error(data.error||'İşlem tamamlanamadı.');
  return data;
}
function fail(target,error) { target.replaceChildren(el('p','error',error.message||String(error))); }
function empty(title,desc,action) { const box=el('div','empty');box.append(el('div','empty-symbol','✎'),el('h3','',title),el('p','',desc)); if(action){const b=el('button','button secondary','İlk sayfanı yaz');b.onclick=()=>openEditor();box.append(b);}return box; }
function invalidateResults(message='Kayıtlar değişti. Güncel bir sonuç için yeniden analiz et.') {
  for(const id of ['ask-result','period-result','helpful-result']) if($(id).childNodes.length) $(id).replaceChildren(el('p','note-panel',message));
}
function navigate(view) {
  const allowed=['journal','ask','period','decisions','helpful','settings']; if(!allowed.includes(view)) view='journal';
  state.view=view;
  document.querySelectorAll('.view').forEach(n=>n.hidden=n.id!=='view-'+view);
  document.querySelectorAll('.nav').forEach(n=>{const active=n.dataset.view===view;n.classList.toggle('active',active);if(active)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
  if(location.hash!=='#'+view) history.replaceState(null,'','#'+view);
  if(view==='decisions') renderDecisions();
  window.scrollTo({top:0,behavior:'instant'});
}
async function refresh() {
  const data=await api('entries');
  if(state.revision!==null && state.revision!==data.revision) invalidateResults();
  state.entries=data.entries;state.revision=data.revision;renderEntries();renderDecisions();
  $('nav-count').textContent=state.entries.length;
}
function renderEntries() {
  const query=$('entry-search').value.toLocaleLowerCase('tr').trim();
  const entries=state.entries.filter(e=>[e.title,e.body,e.reason,e.expectation,e.outcome,e.helpful_note].join(' ').toLocaleLowerCase('tr').includes(query));
  $('entry-count').textContent=state.entries.length+' kayıt';
  const list=$('entries');list.replaceChildren();
  if(!entries.length){list.append(empty(query?'Bu aramada bir sayfa yok.':'İlk izin burada başlayacak.',query?'Farklı bir kelimeyle yeniden ara.':'Bugün aklında kalan bir şeyi yaz. Zamanla kendi hikâyene dönüp bakabileceğin bir alan oluşacak.',!query));return;}
  for(const e of entries){
    const card=el('button','entry-card');card.type='button';card.onclick=()=>openEditor(e.id);
    const meta=el('div','card-meta');meta.append(el('span','',formatDate(e.event_date)),el('span','',e.kind==='decision'?'KARAR':'GÜNLÜK'));
    const bottom=el('div','card-bottom');bottom.append(el('span','pill'+(e.mood==='Zor'||e.mood==='Çok zor'?' warm':''),e.mood||'Etiket yok'),el('span','',e.analyze?'Sayfayı aç ↗':'Analiz dışında · Aç ↗'));
    card.append(meta,el('h3','',e.title),el('p','',e.body),bottom);list.append(card);
  }
}
function renderDecisions(){
  const list=$('decisions');list.replaceChildren();const entries=state.entries.filter(e=>e.kind==='decision');
  if(!entries.length){list.append(empty('Bir karar, bir başlangıç.','Kararının gerekçesini ve beklentini kaydet. Sonucunu daha sonra aynı sayfaya ekleyebilirsin.'));return;}
  for(const e of entries){const box=el('article','decision-card');box.append(el('div','card-meta',formatDate(e.event_date)),el('h2','',e.title));
    const cols=el('div','decision-cols');for(const [key,label,fallback] of [['reason','Gerekçem','Henüz yazılmadı.'],['expectation','Beklentim','Henüz yazılmadı.'],['outcome','Kaydettiğim sonuç','Sonuç henüz kaydedilmedi.']]){const c=el('div');c.append(el('h3','',label),el('p','',e[key]||fallback));cols.append(c);}
    const bottom=el('div','card-bottom');bottom.append(el('span','',e.analyze?'Kendi kaydın · Otomatik yorum içermez':'Kendi kaydın · Analize kapalı'));const b=el('button','button secondary small','Kaydı aç ↗');b.onclick=()=>openEditor(e.id);bottom.append(b);box.append(cols,bottom);list.append(box);
  }
}
function formData(){const data={};for(const key of fields){const input=$(fieldId(key));data[key]=key==='analyze'?input.checked:input.value;}return data;}
function dirty(){return $('editor').open && JSON.stringify(formData())!==state.formSnapshot;}
function closeEditor(force=false){if(!force && dirty() && !confirm('Kaydedilmemiş değişikliklerin var. Kaydetmeden kapatılsın mı?')) return; $('editor').close();}
function openEditor(id=null,kind='journal'){
  const e=id?state.entries.find(e=>e.id===id):null;if(id&&!e){toast('Kayıt bulunamadı. Sayfayı yenile.');return;}
  $('entry-form').reset();$('entry-id').value=id||'';
  for(const key of fields){const input=$(fieldId(key));if(key==='analyze')input.checked=e?e.analyze:true;else input.value=e?e[key]:key==='event_date'?localDay():key==='kind'?kind:'';}
  $('editor-heading').textContent=e?'Sayfana yeniden bak.':'Yeni bir sayfa.';
  $('delete-entry').hidden=!e;$('decision-fields').hidden=$('entry-kind').value!=='decision';
  $('helpful-details').open=!!(e&&e.helpful_note);$('written-at').textContent=e?'Yazıldığı zaman: '+new Date(e.written_at).toLocaleString('tr-TR')+' · Olay tarihi yukarıda ayrı tutulur.':'Yazılma zamanı kaydederken otomatik eklenir.';
  $('editor-error').hidden=true;state.formSnapshot=JSON.stringify(formData());$('editor').showModal();$('entry-title').focus();
}
function setBusy(value){state.busy=value;document.querySelectorAll('#ask-form button[type=submit],#period-form button[type=submit],#helpful-form button[type=submit]').forEach(b=>b.disabled=value);}
function findingNode(f){
  const box=el('article','finding');box.append(el('span','pill',f.kind==='inference'?'Kaynaklı çıkarım':'Yazılanlardan özet'),el('p','',f.text));
  for(const s of f.sources){const b=el('button','source');b.type='button';b.append(el('blockquote','',s.quote),el('small','',`${s.title} · Olay: ${formatDate(s.event_date)} · Yazıldı: ${formatDate(s.written_at)} ↗`));b.onclick=()=>openEditor(s.entry_id);box.append(b);}return box;
}
function resultIntro(){const intro=el('div','result-intro');intro.append(el('span','pill','YEREL ANALİZ'),el('span','','Yorumları özgün alıntılarla kontrol et.'));return intro;}
async function freshResult(result){const latest=await api('revision');if(latest.revision!==result.revision){await refresh();throw new Error('Bu yanıt hazırlanırken kayıtlar değişti. Güncel kayıtlarla yeniden dene.');}}
function coverageNode(c){const box=el('div','note-panel');box.append(el('h3','',`${formatDate(c.start)} — ${formatDate(c.end)}`));const stats=el('div','coverage-stats');for(const [n,label] of [[c.entries,'kayıt okundu'],[c.recorded_days+'/'+c.total_days,'günde kayıt var'],[c.excluded_entries,'kayıt AI dışında']]){const item=el('div');item.append(el('strong','',n),el('span','',label));stats.append(item);}box.append(stats,el('p','hint','Olay tarihlerine göre. Kayıt bulunmaması, o gün bir şey yaşanmadığı anlamına gelmez.'));if(c.gaps.length){const details=el('details');details.append(el('summary','',`Kayıt bulunmayan aralıklar (${c.gaps.length})`));const ul=el('ul','gap-list');for(const g of c.gaps)ul.append(el('li','',g.start===g.end?formatDate(g.start):formatDate(g.start)+' — '+formatDate(g.end)));details.append(ul);box.append(details);}return box;}
function renderAnalysis(target,result){
  target.replaceChildren(resultIntro(),coverageNode(result.coverage));
  if(result.message)target.append(el('p','note-panel',result.message));
  if(result.overview.length){target.append(el('h2','','Döneme bir bakış'));for(const f of result.overview)target.append(findingNode(f));}
  for(const s of result.sections){const head=el('div','month-header');head.append(el('h2','',formatDate(s.month,true)),el('span','hint',s.entries+' kayıt'));target.append(head);if(result.mode==='period'){const moods=el('div','mood-list');for(const [m,count] of Object.entries(s.moods))moods.append(el('span','pill',m+' · '+count));target.append(el('p','hint','Kendi duygu etiketlerin · Otomatik atanmaz'),moods);}for(const f of s.findings)target.append(findingNode(f));if(!s.findings.length)target.append(el('p','hint','Bu ay için doğrulanabilir bir bulgu üretilmedi.'));}
  if(result.rejected_findings)target.append(el('p','hint','Kaynağı doğrulanamayan bazı otomatik bulgular gösterilmedi.'));
}
async function analyze(mode){
  if(state.busy)return;const prefix=mode==='period'?'period':'helpful',target=$(prefix+'-result');
  setBusy(true);target.replaceChildren(el('div','loading','Günlüklerin bilgisayarında okunuyor. Uzun dönemlerde bu işlem birkaç dakika sürebilir.'));
  try {const result=await api('insights',{method:'POST',body:JSON.stringify({start:$(prefix+'-start').value,end:$(prefix+'-end').value,mode})});await freshResult(result);renderAnalysis(target,result);}catch(e){fail(target,e);}finally{setBusy(false);}
}
async function checkAI(){
  $('check-ai').disabled=true;
  try{const data=await api('status');$('ai-status').textContent=data.ready?'● Yerel analiz hazır':'○ Yerel analiz hazır değil';$('ai-status').classList.toggle('ready',data.ready);$('model-title').textContent=data.ready?'Her şey burada çalışıyor.':'Model kurulumunu tamamla.';
    $('model-detail').textContent=data.ready?`${data.model} · ${data.embedding_model}`:data.error||'Eksik modeller: '+data.missing.join(', ');
    $('model-commands').hidden=data.ready;$('model-commands').textContent='Proje klasöründe kurulum:\npython3 scripts/setup.py\n\nArdından Başlat.command dosyasını aç.';
  }catch(e){$('ai-status').textContent='Bağlantı kesildi';$('model-title').textContent='Uygulamaya ulaşılamadı.';$('model-detail').textContent=e.message;}finally{$('check-ai').disabled=false;}
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>navigate(b.dataset.view));
$('new-top').onclick=$('new-hero').onclick=()=>openEditor();$('new-decision').onclick=()=>openEditor(null,'decision');$('close-editor').onclick=()=>closeEditor();
$('editor').addEventListener('cancel',e=>{e.preventDefault();closeEditor();});
$('entry-kind').onchange=()=>$('decision-fields').hidden=$('entry-kind').value!=='decision';
$('entry-search').oninput=renderEntries;
$('entry-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('editor-error').hidden=true;try{const id=$('entry-id').value;await api('entries'+(id?'/'+id:''),{method:id?'PUT':'POST',body:JSON.stringify(formData())});closeEditor(true);await refresh();toast('Sayfan kaydedildi.');}catch(err){$('editor-error').textContent=err.message;$('editor-error').hidden=false;}finally{b.disabled=false;}};
$('delete-entry').onclick=async()=>{if(!confirm('Bu kayıt ve ona ait arama verileri kalıcı olarak silinsin mi?'))return;try{await api('entries/'+$('entry-id').value,{method:'DELETE'});closeEditor(true);await refresh();toast('Kayıt silindi.');}catch(e){toast(e.message);}};
document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>{$('question').value=b.dataset.question;$('question').focus();});
$('ask-form').onsubmit=async e=>{e.preventDefault();if(state.busy)return;setBusy(true);const target=$('ask-result');target.replaceChildren(el('div','loading','Kaynakların bilgisayarında aranıyor…'));
  try{const result=await api('ask',{method:'POST',body:JSON.stringify({question:$('question').value,start:$('ask-start').value,end:$('ask-end').value})});await freshResult(result);target.replaceChildren(resultIntro());if(result.message)target.append(el('p','note-panel',result.message));for(const f of result.findings)target.append(findingNode(f));target.append(el('p','hint',`${result.searched_entries} izinli kayıtta arandı · ${result.used_entries} kaynağa dayalı yanıt. Bu arama tüm dönemin kapsamlı analizi değildir; bunun için Zaman içinde ekranını kullan.`));if(result.rejected_findings)target.append(el('p','hint','Kaynağı doğrulanamayan bazı otomatik bulgular gösterilmedi.'));}catch(err){fail(target,err);}finally{setBusy(false);}};
$('period-form').onsubmit=e=>{e.preventDefault();analyze('period');};$('helpful-form').onsubmit=e=>{e.preventDefault();analyze('helpful');};$('check-ai').onclick=checkAI;
$('export').onclick=async()=>{try{const data=await api('backup');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download='iz-yedek-'+localDay()+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Yedeğin indirildi. Güvenli bir yerde sakla.');}catch(e){toast(e.message);}};
$('restore').onclick=async()=>{const file=$('backup-file').files[0];if(!file){toast('Önce bir JSON yedek dosyası seç.');return;}if(!confirm('Bu yedek mevcut TÜM kayıtların yerini alacak. Güncel yedeğini indirdiğinden emin misin?'))return;const b=$('restore');b.disabled=true;try{const backup=JSON.parse(await file.text());const result=await api('restore',{method:'POST',body:JSON.stringify({confirm_replace:true,backup})});await refresh();$('backup-file').value='';toast(result.count+' kayıt geri yüklendi.');}catch(e){toast(e instanceof SyntaxError?'Geçerli bir JSON yedek dosyası seç.':e.message);}finally{b.disabled=false;}};
window.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
document.querySelector('.skip').onclick=e=>{e.preventDefault();$('main').focus();};
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
$('today').textContent=new Date().toLocaleDateString('tr-TR',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
const today=localDay(),yearAgo=new Date();yearAgo.setFullYear(yearAgo.getFullYear()-1);const start=`${yearAgo.getFullYear()}-${String(yearAgo.getMonth()+1).padStart(2,'0')}-${String(yearAgo.getDate()).padStart(2,'0')}`;
for(const prefix of ['period','helpful']){$(prefix+'-start').value=start;$(prefix+'-end').value=today;}
navigate(location.hash.slice(1));refresh().catch(e=>fail($('entries'),e));checkAI();
// Clear visible derived results on changes from another tab; nothing is cached in browser storage.
setInterval(async()=>{if(document.hidden)return;try{const data=await api('revision');if(state.revision!==null&&data.revision!==state.revision)await refresh();}catch{}},4000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh().catch(()=>{});});
