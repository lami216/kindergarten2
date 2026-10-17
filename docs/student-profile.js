/* Synthetic per-tab portraits only; real private storage is student_photos.py. */
const studentPortraits=new Map();
recordNames.student_photos='صور الطلاب';
Object.assign(historyFields,{photo:'الصورة',revision:'نسخة الصورة',sha256:'بصمة الصورة'});
const profileCan=(action)=>demoCan('students',action);
function portraitMeta(s,p){return {name:s.name,photo:p?.data?'صورة محفوظة':'بلا صورة',revision:p?.revision||0,sha256:p?.sha256||''};}
function profileAge(birth){
 const d=new Date(birth+'T00:00:00'),now=new Date();if(!birth||Number.isNaN(+d))return 'غير مسجل';
 let years=now.getFullYear()-d.getFullYear();if(now.getMonth()<d.getMonth()||(now.getMonth()===d.getMonth()&&now.getDate()<d.getDate()))years--;
 return years>=0?`${years} سنوات`:'غير مسجل';
}
function fileFields(entries){return `<div class="file-details">${entries.map(([label,value])=>`<div><small>${esc(label)}</small><p>${esc(value||'غير مسجل')}</p></div>`).join('')}</div>`;}
profile=function(){
 const s=students.find(s=>s.id===profileId),a=account(s),p=studentPortraits.get(s.id);
 const image=p?.data?`<img class="file-portrait" src="${p.data}" alt="صورة ${esc(s.name)}">`:`<span class="file-portrait file-initial" role="img" aria-label="لم تضف صورة للطالب">${esc(s.name[0])}</span>`;
 const photos=profileCan('edit')?`<details class="file-photo-editor"><summary>📷 ${p?.data?'تغيير / حذف صورة الطالب':'إضافة صورة الطالب'}</summary><form id="profile-photo-form" class="body-space" data-revision="${p?.revision||0}"><label>اختر صورة الطالب<input id="profile-photo-file" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="muted">JPG أو PNG أو WebP، حتى 5 ميغابايت. تُحفظ مصغرة دون بيانات الموقع والكاميرا.</p><div id="profile-photo-preview"></div><label>سبب تغيير الصورة *<input name="reason" required maxlength="2000"></label><div class="actions body-space"><button class="primary" id="profile-photo-save" ${s.cancelled?'disabled':''}>حفظ الصورة</button></div><p class="error" id="profile-photo-error" role="alert"></p></form>${p?.data?`<form id="profile-photo-remove" class="body-space" data-revision="${p.revision}"><label>سبب حذف الصورة *<input name="reason" required maxlength="2000"></label><label class="check-row"><input name="confirm" type="checkbox" required> أؤكد حذف صورة الطالب فقط، مع بقاء ملفه</label><button class="secondary danger">حذف الصورة</button><p class="error" id="profile-photo-remove-error" role="alert"></p></form>`:''}</details>`:'';
 const finance=demoCan('receipts')?`<section class="panel"><div class="panel-title"><h2>💵 الحساب المالي</h2><span class="muted">أوقية قديمة</span></div><div class="stats three">${stat('💵','مجموع المدفوع',money(a.paid),'أوقية قديمة')}${stat('⏳','الباقي للدفع الآن',money(a.due),'أوقية قديمة','#b45309','#fffbeb')}${stat('📅','الرسوم',s.exempt?'معفي':'عادي','')}</div><div class="actions body-space">${!s.exempt&&!s.cancelled&&demoCan('receipts','create')?'<button class="secondary" id="profile-pay">💵 تسجيل دفعة</button>':''}<button class="secondary" id="profile-receipts">🧾 عرض الوصولات</button></div></section>`:'';
 const edit=!s.cancelled&&profileCan('edit')?`<details class="panel"><summary>✏️ تعديل بيانات الطالب</summary><form id="edit-child" class="body-space"><div class="form-grid"><label>اسم الطفل *<input name="name" required maxlength="100" value="${esc(s.name)}"></label><label>تاريخ الميلاد<input type="date" name="birth" max="${today}" value="${esc(s.birth||'')}"></label><label>الجنس<select name="gender"><option ${s.gender==='ذكر'?'selected':''}>ذكر</option><option ${s.gender==='أنثى'?'selected':''}>أنثى</option></select></label><label>مكان الميلاد<input name="place" maxlength="100" value="${esc(s.place||'')}"></label><label>العنوان<input name="address" value="${esc(s.address||'')}"></label></div><div class="form-grid body-space"><label>ملاحظات صحية<textarea name="health">${esc(s.health||'')}</textarea></label><label>الحساسية<textarea name="allergy">${esc(s.allergy||'')}</textarea></label><label>ملاحظات عامة<textarea name="notes">${esc(s.notes||'')}</textarea></label></div><div class="form-end"><button class="primary">حفظ التعديلات</button></div><p class="error" id="profile-edit-error" role="alert"></p></form></details>`:'';
 return heading('ملف الطالب','صورة واضحة، وبيانات مرتبة، وحساب في مكانه.','<button class="secondary" id="back-students">العودة للطلاب</button>')+`<section class="panel file-hero">${image}<div class="file-identity"><small class="muted">ملف الطالب</small><h2>${esc(s.name)}</h2><p class="muted">${esc(s.gender||'')} · العمر: ${profileAge(s.birth)}</p><div class="actions"><span class="status">${esc(s.class||'بدون قسم')}</span><span class="status ${s.cancelled?'amber':''}">${s.cancelled?'مؤرشف':'ملف نشط'}</span></div></div></section>${photos?`<div class="panel">${photos}</div>`:''}${finance}<div class="two-col file-info"><section class="panel"><h2>🎒 بيانات الطفل</h2>${fileFields([['تاريخ الميلاد',s.birth],['مكان الميلاد',s.place],['العنوان',s.address],['الجنس',s.gender]])}</section><section class="panel"><h2>☎️ التواصل مع الأسرة</h2>${fileFields([['اسم الأب',s.fatherName||(!s.motherName?s.parent:'')],['هاتف الأب',s.fatherPhone||(!s.motherPhone?s.phone:'')],['اسم الأم',s.motherName],['هاتف الأم',s.motherPhone]])}</section></div>${s.health||s.allergy||s.notes?`<section class="panel"><h2>🩺 الصحة والملاحظات</h2>${fileFields([['ملاحظات صحية',s.health],['الحساسية',s.allergy],['ملاحظات عامة',s.notes]].filter(e=>e[1]))}</section>`:''}${edit}${profileCan('cancel')?`<details class="panel"><summary>إدارة وأرشفة الملف</summary><div class="body-space">${recordActions('students',s.id,s.cancelled)}</div></details>`:''}`;
};

async function normalizePortrait(file){
 if(!file)throw Error('اختر صورة أولًا.');
 if(file.size>5*1024*1024)throw Error('حجم الصورة أكبر من 5 ميغابايت؛ اختر صورة أصغر.');
 const bytes=new Uint8Array(await file.arrayBuffer());
 const png=bytes[0]===137&&bytes[1]===80&&bytes[2]===78&&bytes[3]===71;
 const jpg=bytes[0]===255&&bytes[1]===216&&bytes[2]===255;
 const webp=new TextDecoder().decode(bytes.slice(0,4))==='RIFF'&&new TextDecoder().decode(bytes.slice(8,12))==='WEBP';
 if(!['image/jpeg','image/png','image/webp'].includes(file.type)||!(png||jpg||webp))throw Error('اختر ملف صورة سليمًا بصيغة JPG أو PNG أو WebP.');
 if(webp){const view=new DataView(bytes.buffer);for(let offset=12;offset+8<=bytes.length;){const tag=new TextDecoder().decode(bytes.slice(offset,offset+4)),size=view.getUint32(offset+4,true);if(tag==='ANIM'||tag==='ANMF')throw Error('اختر صورة ثابتة، وليست صورة متحركة.');offset+=8+size+(size%2);}}
 let bitmap;try{bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});}catch{throw Error('تعذّر قراءة الصورة؛ اختر ملف صورة سليمًا.');}
 try{
  if(bitmap.width*bitmap.height>12000000)throw Error('أبعاد الصورة كبيرة جدًا؛ اختر صورة أصغر من 12 مليون بكسل.');
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
   try{const p=await normalizePortrait(e.target.files[0]);if(current!==selection)return;prepared=p;$('#profile-photo-preview').innerHTML=`<img class="file-preview" src="${p.data}" alt="معاينة صورة الطالب قبل الحفظ">`;}
   catch(error){if(current===selection)$('#profile-photo-error').textContent=error.message;}
   finally{if(current===selection)preparing=false;}
  };
  f.onsubmit=e=>{
   e.preventDefault();if(!f.reportValidity())return;
   try{
    if(!profileCan('edit')||students.find(s=>s.id===sid).cancelled)throw Error('لا يمكن تغيير الصورة لهذا الملف.');
    if(preparing)throw Error('انتظر اكتمال معاينة الصورة.');if(!prepared)throw Error('اختر صورة سليمة أولًا.');
    const old=studentPortraits.get(sid);if((old?.revision||0)!==+f.dataset.revision)throw Error('تغيّرت الصورة؛ افتح الملف مجددًا.');
    const s=students.find(s=>s.id===sid),p={...prepared,revision:(old?.revision||0)+1};studentPortraits.set(sid,p);
    logChange('student_photos',sid,old?.data?'updated':'created',portraitMeta(s,old),portraitMeta(s,p),new FormData(f).get('reason').trim());render();toast('حُفظت صورة الطالب.');
   }catch(error){$('#profile-photo-error').textContent=error.message;}
  };
 }
 const removal=$('#profile-photo-remove');if(removal)removal.onsubmit=e=>{
  e.preventDefault();if(!removal.reportValidity()||!profileCan('edit'))return;
  const old=studentPortraits.get(profileId);if(old?.revision!==+removal.dataset.revision){$('#profile-photo-remove-error').textContent='تغيّرت الصورة؛ افتح الملف مجددًا.';return;}
  const s=students.find(s=>s.id===profileId),next={revision:old.revision+1,data:null};studentPortraits.set(s.id,next);
  logChange('student_photos',s.id,'deleted',portraitMeta(s,old),portraitMeta(s,next),new FormData(removal).get('reason').trim());render();toast('حُذفت الصورة؛ بقي ملف الطالب محفوظًا.');
 };
 const edit=$('#edit-child');if(edit){const id=profileId,snapshot=JSON.stringify(students.find(s=>s.id===id));edit.onsubmit=e=>{
  e.preventDefault();if(!edit.reportValidity()||!profileCan('edit'))return;
  const s=students.find(s=>s.id===id),d=new FormData(edit),error=$('#profile-edit-error');
  if(s.cancelled||JSON.stringify(s)!==snapshot){error.textContent='تغيّر الملف؛ افتحه مجددًا قبل التعديل.';return;}
  const before=copy(s);Object.assign(s,{name:d.get('name').trim(),birth:d.get('birth'),gender:d.get('gender'),place:d.get('place').trim(),address:d.get('address').trim(),health:d.get('health').trim(),allergy:d.get('allergy').trim(),notes:d.get('notes').trim()});
  if(!s.name){Object.assign(s,before);error.textContent='اكتب اسم الطفل.';return;}
  logChange('students',id,'updated',before,s,'تعديل بيانات الطالب من ملفه');render();toast('حُفظت بيانات الطالب.');
 };}
};

const profileStudentForm=studentForm;
studentForm=()=>profileStudentForm().replace('<h2 class="student-section-title">٢ · بيانات الأهل</h2>',`<details class="file-intake-photo"><summary>📷 صورة الطالب (اختياري)</summary><label class="body-space">صورة الطفل<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="muted">حتى 5 ميغابايت. يمكنك إضافتها لاحقًا من ملف الطالب.</p><div id="intake-photo-preview"></div></details><h2 class="student-section-title">٢ · بيانات الأهل</h2>`);
const profileBindStudentForm=bindStudentForm;
bindStudentForm=function(){
 profileBindStudentForm();const f=$('#student-form'),submit=f.onsubmit;let prepared=null,invalid=false,busy=false,selection=0;
 f.querySelector('[name="photo"]').onchange=async e=>{
  const current=++selection;prepared=null;invalid=false;busy=true;
  try{if(!e.target.files.length){$('#intake-photo-preview').textContent='';return;}const p=await normalizePortrait(e.target.files[0]);if(current!==selection)return;prepared=p;$('#intake-photo-preview').innerHTML=`<img class="file-preview" src="${p.data}" alt="معاينة صورة الطفل">`;$('#student-error').textContent='';}
  catch(error){if(current===selection){invalid=true;$('#intake-photo-preview').textContent='';$('#student-error').textContent=error.message;}}
  finally{if(current===selection)busy=false;}
 };
 f.onsubmit=e=>{
  e.preventDefault();if(busy||invalid){$('#student-error').textContent=busy?'انتظر اكتمال معاينة الصورة.':'اختر صورة سليمة أو أزل الملف المختار.';return;}
  const count=students.length,portrait=prepared,d=new FormData(f);submit(e);
  if(students.length>count){const s=students.at(-1);Object.assign(s,{place:d.get('place')?.trim()||'',address:d.get('address')?.trim()||'',health:d.get('health')?.trim()||''});if(portrait){const p={...portrait,revision:1};studentPortraits.set(s.id,p);logChange('student_photos',s.id,'created',null,portraitMeta(s,p),'صورة مع تسجيل الطالب');}}
 };
};
