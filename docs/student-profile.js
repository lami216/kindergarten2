/* Synthetic per-tab portraits only; real private storage is student_photos.py. */
const studentPortraits=new Map();
recordNames.student_photos=`${I18N.tr("ui.51f238d4c59d")}`;
Object.assign(historyFields,{photo:`${I18N.tr("ui.a35a713b5b75")}`,revision:`${I18N.tr("ui.c2c923f54cd4")}`,sha256:`${I18N.tr("ui.4e0e6ee82e19")}`});
const profileCan=(action)=>demoCan('students',action);
function portraitMeta(s,p){return {name:s.name,photo:p?.data?`${I18N.tr("ui.6da84d413b2e")}`:`${I18N.tr("ui.19c296277d37")}`,revision:p?.revision||0,sha256:p?.sha256||''};}
function profileAge(birth){
 const d=new Date(birth+'T00:00:00'),now=new Date();if(!birth||Number.isNaN(+d))return `${I18N.tr("ui.fdb8ba844e96")}`;
 let years=now.getFullYear()-d.getFullYear();if(now.getMonth()<d.getMonth()||(now.getMonth()===d.getMonth()&&now.getDate()<d.getDate()))years--;
 return years>=0?`${I18N.tr("ui.9bef57cd8443",{p0:years})}`:`${I18N.tr("ui.fdb8ba844e96")}`;
}
function fileFields(entries){return `<div class="file-details">${entries.map(([label,value])=>`<div><small>${esc(label)}</small><p>${esc(value||`${I18N.tr("ui.fdb8ba844e96")}`)}</p></div>`).join('')}</div>`;}
profile=function(){
 const s=students.find(s=>s.id===profileId),a=account(s),p=studentPortraits.get(s.id);
 const image=p?.data?`<img class="file-portrait" src="${p.data}" alt="${I18N.tr("ui.89f41c08024e",{p0:esc(s.name)})}">`:`<span class="file-portrait file-initial" role="img" aria-label="${I18N.tr("ui.ceee2e6bcd2c")}">${esc(s.name[0])}</span>`;
 const photos=profileCan('edit')?`<details class="file-photo-editor"><summary>📷 ${p?.data?`${I18N.tr("ui.a73d7576516a")}`:`${I18N.tr("ui.6b474fb54e36")}`}</summary><form id="profile-photo-form" class="body-space" data-revision="${p?.revision||0}"><label>${I18N.tr("ui.9b60b76ffcbb")}<input id="profile-photo-file" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="muted">${I18N.tr("ui.f275145cfae8")}</p><div id="profile-photo-preview"></div><label>${I18N.tr("ui.e33d9ca7e960")}<input name="reason" required maxlength="2000"></label><div class="actions body-space"><button class="primary" id="profile-photo-save" ${s.cancelled?'disabled':''}>${I18N.tr("ui.21d82bd3f3b1")}</button></div><p class="error" id="profile-photo-error" role="alert"></p></form>${p?.data?`<form id="profile-photo-remove" class="body-space" data-revision="${p.revision}"><label>${I18N.tr("ui.bea57ec23c87")}<input name="reason" required maxlength="2000"></label><label class="check-row"><input name="confirm" type="checkbox" required> ${I18N.tr("ui.b58e03499815")}</label><button class="secondary danger">${I18N.tr("ui.8119b8d211c3")}</button><p class="error" id="profile-photo-remove-error" role="alert"></p></form>`:''}</details>`:'';
 const finance=demoCan('receipts')?`<section class="panel"><div class="panel-title"><h2>${I18N.tr("ui.f82df5c04512")}</h2><span class="muted">${I18N.tr("ui.894811c10b8d")}</span></div><div class="stats">${stat('💵','مجموع المدفوع',money(a.paid),'أوقية قديمة')}${stat('⏳','الباقي للدفع الآن',money(a.due),'أوقية قديمة','#b45309','#fffbeb')}</div><p class="muted body-space">${I18N.tr("ui.3eb7f9cea6ef",{p0:s.exempt?I18N.enumLabel('exempt'):`${I18N.tr("ui.f3569af24500")}`})}</p><div class="actions body-space">${!s.exempt&&!s.cancelled&&demoCan('receipts','create')?`<button class="secondary" id="profile-pay">${I18N.tr("ui.153fa1722db4")}</button>`:''}<button class="secondary" id="profile-receipts">${I18N.tr("ui.45922b7b72cf")}</button></div></section>`:'';
 const edit=!s.cancelled&&profileCan('edit')?`<details class="panel"><summary>${I18N.tr("ui.6ae5cc43e3c2")}</summary><form id="profile-edit-child" class="body-space"><div class="form-grid"><label>${I18N.tr("ui.73dcb3987ac4")}<input name="name" required maxlength="100" value="${esc(s.name)}"></label><label>${I18N.tr("ui.3364645354dd")}<input type="date" name="birth" max="${today}" value="${esc(s.birth||'')}"></label><label>${I18N.tr("ui.a79dffdd2070")}<select name="gender"><option ${s.gender==='ذكر'?'selected':''} value="ذكر">${I18N.tr("ui.2f13379bf81e")}</option><option ${s.gender==='أنثى'?'selected':''} value="أنثى">${I18N.tr("ui.d2ee47ec7d05")}</option></select></label><label>${I18N.tr("ui.96af33aaef70")}<input name="place" maxlength="100" value="${esc(s.place||'')}"></label><label>${I18N.tr("ui.2d110e56d5f5")}<input name="address" value="${esc(s.address||'')}"></label></div><div class="form-grid body-space"><label>${I18N.tr("ui.0b59767c4462")}<textarea name="health">${esc(s.health||'')}</textarea></label><label>${I18N.tr("ui.cac91adad141")}<textarea name="allergy">${esc(s.allergy||'')}</textarea></label><label>${I18N.tr("ui.b82bbcf765a8")}<textarea name="notes">${esc(s.notes||'')}</textarea></label></div><div class="form-end"><button class="primary">${I18N.tr("ui.6c03d6737c2f")}</button></div><p class="error" id="profile-edit-error" role="alert"></p></form></details>`:'';
 return `${heading(`${I18N.tr("ui.ab48f36beeaa")}`,`${I18N.tr("ui.d1e8978b1751")}`,`<button class="secondary" id="back-students">${I18N.tr("ui.3c44b865bc5f")}</button>`)}<section class="panel file-hero">${image}<div class="file-identity"><small class="muted">${I18N.tr("ui.ab48f36beeaa")}</small><h2>${esc(s.name)}</h2><p class="muted">${I18N.tr("ui.45d6062be292",{p0:esc(I18N.enumLabel(s.gender||'')),p1:profileAge(s.birth)})}</p><div class="actions"><span class="status">${esc(s.class||`${I18N.tr("ui.856755e3c953")}`)}</span><span class="status ${s.cancelled?'amber':''}">${s.cancelled?`${I18N.tr("ui.9d1b78e3b949")}`:`${I18N.tr("ui.d04634d8ef3f")}`}</span></div></div></section>${photos?`<div class="panel">${photos}</div>`:''}${finance}<div class="two-col file-info"><section class="panel"><h2>${I18N.tr("ui.3e96ad5466d1")}</h2>${fileFields([[`${I18N.tr("ui.3364645354dd")}`,s.birth],[`${I18N.tr("ui.96af33aaef70")}`,s.place],[`${I18N.tr("ui.2d110e56d5f5")}`,s.address],[`${I18N.tr("ui.a79dffdd2070")}`,I18N.enumLabel(s.gender)]])}</section><section class="panel"><h2>${I18N.tr("ui.b3c275aa6ea2")}</h2>${fileFields([[`${I18N.tr("ui.3c571949c936")}`,s.fatherName||(!s.motherName?s.parent:'')],[`${I18N.tr("ui.a84e401aadf5")}`,s.fatherPhone||(!s.motherPhone?s.phone:'')],[`${I18N.tr("ui.529a1e93a7ba")}`,s.motherName],[`${I18N.tr("ui.faee701516d5")}`,s.motherPhone]])}</section></div>${s.health||s.allergy||s.notes?`<section class="panel"><h2>${I18N.tr("ui.0bcc5d9f536c")}</h2>${fileFields([[`${I18N.tr("ui.0b59767c4462")}`,s.health],[`${I18N.tr("ui.cac91adad141")}`,s.allergy],[`${I18N.tr("ui.b82bbcf765a8")}`,s.notes]].filter(e=>e[1]))}</section>`:''}${edit}${profileCan('cancel')?`<details class="panel"><summary>${I18N.tr("ui.70e0559d9c39")}</summary><div class="body-space">${recordActions('students',s.id,s.cancelled)}</div></details>`:''}`;
};

async function normalizePortrait(file){
 if(!file)throw Error(`${I18N.tr("ui.61c9fb57f9fd")}`);
 if(file.size>5*1024*1024)throw Error(`${I18N.tr("ui.4e615b73763d")}`);
 const bytes=new Uint8Array(await file.arrayBuffer());
 const png=bytes[0]===137&&bytes[1]===80&&bytes[2]===78&&bytes[3]===71;
 const jpg=bytes[0]===255&&bytes[1]===216&&bytes[2]===255;
 const webp=new TextDecoder().decode(bytes.slice(0,4))==='RIFF'&&new TextDecoder().decode(bytes.slice(8,12))==='WEBP';
 if(!['image/jpeg','image/png','image/webp'].includes(file.type)||!(png||jpg||webp))throw Error(`${I18N.tr("ui.298ebc481194")}`);
 if(webp){const view=new DataView(bytes.buffer);for(let offset=12;offset+8<=bytes.length;){const tag=new TextDecoder().decode(bytes.slice(offset,offset+4)),size=view.getUint32(offset+4,true);if(tag==='ANIM'||tag==='ANMF')throw Error(`${I18N.tr("ui.3a187478b5df")}`);offset+=8+size+(size%2);}}
 let bitmap;try{bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});}catch{throw Error(`${I18N.tr("ui.4bf7c047660b")}`);}
 try{
  if(bitmap.width*bitmap.height>12000000)throw Error(`${I18N.tr("ui.31e34316772a")}`);
  const scale=Math.min(1,640/bitmap.width,640/bitmap.height),canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
  const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
  const data=canvas.toDataURL('image/jpeg',.86),sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(data))),b=>b.toString(16).padStart(2,'0')).join('');
  return {data,sha256};
 }finally{bitmap.close();}
}

const profileBaseBind=bind;
bind=function(){
 profileBaseBind();
 const f=$('#profile-photo-form');
 if(f){
  const sid=profileId;let prepared=null,preparing=false,selection=0;
  $('#profile-photo-file').onchange=async e=>{
   const current=++selection;preparing=true;prepared=null;$('#profile-photo-preview').textContent='';$('#profile-photo-error').textContent='';
   try{const p=await normalizePortrait(e.target.files[0]);if(current!==selection||!f.isConnected)return;prepared=p;$('#profile-photo-preview').innerHTML=`<img class="file-preview" src="${p.data}" alt="${I18N.tr("ui.0b24dd367c12")}">`;}
   catch(error){if(current===selection&&f.isConnected)$('#profile-photo-error').textContent=error.message;}
   finally{if(current===selection)preparing=false;}
  };
  f.onsubmit=e=>{
   e.preventDefault();if(!f.reportValidity())return;
   try{
    if(!profileCan('edit')||students.find(s=>s.id===sid).cancelled)throw Error(`${I18N.tr("ui.91ddaa03961d")}`);
    if(preparing)throw Error(`${I18N.tr("ui.43504fa0ef22")}`);if(!prepared)throw Error(`${I18N.tr("ui.d994afc20b46")}`);
    const old=studentPortraits.get(sid);if((old?.revision||0)!==+f.dataset.revision)throw Error(`${I18N.tr("ui.b50e40b2a9b1")}`);
    const s=students.find(s=>s.id===sid),p={...prepared,revision:(old?.revision||0)+1};studentPortraits.set(sid,p);
    logChange('student_photos',sid,old?.data?'updated':'created',portraitMeta(s,old),portraitMeta(s,p),new FormData(f).get('reason').trim());render();toast(`${I18N.tr("ui.04f075074824")}`);
   }catch(error){$('#profile-photo-error').textContent=error.message;}
  };
 }
 const removal=$('#profile-photo-remove');if(removal)removal.onsubmit=e=>{
  e.preventDefault();if(!removal.reportValidity()||!profileCan('edit'))return;
  const old=studentPortraits.get(profileId);if(old?.revision!==+removal.dataset.revision){$('#profile-photo-remove-error').textContent=`${I18N.tr("ui.b50e40b2a9b1")}`;return;}
  const s=students.find(s=>s.id===profileId),next={revision:old.revision+1,data:null};studentPortraits.set(s.id,next);
  logChange('student_photos',s.id,'deleted',portraitMeta(s,old),portraitMeta(s,next),new FormData(removal).get('reason').trim());render();toast(`${I18N.tr("ui.fc1416982045")}`);
 };
 const edit=$('#profile-edit-child');if(edit){const id=profileId,snapshot=JSON.stringify(students.find(s=>s.id===id));edit.onsubmit=e=>{
  e.preventDefault();if(!edit.reportValidity()||!profileCan('edit'))return;
  const s=students.find(s=>s.id===id),d=new FormData(edit),error=$('#profile-edit-error');
  if(s.cancelled||JSON.stringify(s)!==snapshot){error.textContent=`${I18N.tr("ui.ee70de9c5f22")}`;return;}
  const before=copy(s);Object.assign(s,{name:d.get('name').trim(),birth:d.get('birth'),gender:d.get('gender'),place:d.get('place').trim(),address:d.get('address').trim(),health:d.get('health').trim(),allergy:d.get('allergy').trim(),notes:d.get('notes').trim()});
  if(!s.name){Object.assign(s,before);error.textContent=`${I18N.tr("ui.20f3b35f853f")}`;return;}
  logChange('students',id,'updated',before,s,`${I18N.tr("ui.4141b5d2b7ab")}`);render();toast(`${I18N.tr("ui.ecb302bd2e43")}`);
 };}
};

const profileStudentForm=studentForm;
studentForm=()=>profileStudentForm().replace(`<h2 class="student-section-title">${I18N.tr("ui.aeb42b3a3c6e")}</h2>`,`<details class="file-intake-photo"><summary>${I18N.tr("ui.8bcf33839890")}</summary><label class="body-space">${I18N.tr("ui.f26d23ec4f68")}<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="muted">${I18N.tr("ui.204732635ee0")}</p><div id="intake-photo-preview"></div></details><h2 class="student-section-title">${I18N.tr("ui.aeb42b3a3c6e")}</h2>`);
const profileBindStudentForm=bindStudentForm;
bindStudentForm=function(){
 profileBindStudentForm();const f=$('#student-form'),submit=f.onsubmit;let prepared=null,invalid=false,busy=false,selection=0;
 f.querySelector('[name="photo"]').onchange=async e=>{
  const current=++selection;prepared=null;invalid=false;busy=true;
  try{if(!e.target.files.length){$('#intake-photo-preview').textContent='';return;}const p=await normalizePortrait(e.target.files[0]);if(current!==selection||!f.isConnected)return;prepared=p;$('#intake-photo-preview').innerHTML=`<img class="file-preview" src="${p.data}" alt="${I18N.tr("ui.f15e2b800f64")}">`;$('#student-error').textContent='';}
  catch(error){if(current===selection){invalid=true;$('#intake-photo-preview').textContent='';$('#student-error').textContent=error.message;}}
  finally{if(current===selection)busy=false;}
 };
 f.onsubmit=e=>{
  e.preventDefault();if(busy||invalid){$('#student-error').textContent=busy?`${I18N.tr("ui.43504fa0ef22")}`:`${I18N.tr("ui.a515243e0fbc")}`;return;}
  const count=students.length,portrait=prepared,d=new FormData(f);submit(e);
  if(students.length>count){const s=students.at(-1);Object.assign(s,{place:d.get('place')?.trim()||'',address:d.get('address')?.trim()||'',health:d.get('health')?.trim()||''});if(portrait){const p={...portrait,revision:1};studentPortraits.set(s.id,p);logChange('student_photos',s.id,'created',null,portraitMeta(s,p),`${I18N.tr("ui.f059d2b65ba1")}`);}}
 };
};
