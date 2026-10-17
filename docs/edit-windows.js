/* The Pages interaction model uses the same protected-window workflow. */
function formSignature(dialog){
 return JSON.stringify([...dialog.querySelectorAll('input,select,textarea')].map(e=>[
  e.name||e.id,e.type==='checkbox'?e.checked:e.type==='file'?[...e.files].map(f=>[f.name,f.size,f.lastModified]):e.value
 ]));
}
function protectEditWindow(dialog,closeIds=[]){
 const initial=formSignature(dialog);
 const close=()=>{dialog.close();if(dialog.id.startsWith('profile-'))render();};
 const requestClose=()=>{
  if(formSignature(dialog)===initial){close();return;}
  if(dialog.querySelector('.discard-box'))return;
  const box=document.createElement('div');box.className='discard-box';box.setAttribute('role','alert');
  box.innerHTML='<p>لديك تغييرات غير محفوظة. هل تريد تجاهلها والخروج؟</p><div class="actions"><button type="button" class="danger" data-discard>تجاهل التغييرات والخروج</button><button type="button" class="secondary" data-keep>متابعة التعديل</button></div>';
  dialog.append(box);box.querySelector('[data-discard]').onclick=()=>{dialog.querySelectorAll('form').forEach(f=>f.reset());close();};
  box.querySelector('[data-keep]').onclick=()=>box.remove();box.querySelector('[data-keep]').focus();
 };
 dialog.oncancel=e=>{e.preventDefault();requestClose();};
 dialog.onclick=e=>{if(e.target===dialog)requestClose();};
 for(const id of closeIds){const b=dialog.querySelector('#'+id);if(b)b.onclick=requestClose;}
 dialog.dataset.protected='true';dialog._initialSignature=initial;
}
window.addEventListener('beforeunload',e=>{
 if([...document.querySelectorAll('dialog[open][data-protected]')].some(d=>formSignature(d)!==d._initialSignature)){e.preventDefault();e.returnValue='';}
});
const windowProfile=profile;
profile=function(){
 const template=document.createElement('template');template.innerHTML=windowProfile();
 const s=students.find(x=>x.id===profileId),root=template.content,hero=root.querySelector('.file-hero'),identity=root.querySelector('.file-identity');
 const description=identity.querySelector('p');
 description.outerHTML=`<div class="file-tags"><span class="status ${s.gender==='ذكر'?'boy':s.gender==='أنثى'?'girl':''}">${esc(s.gender||'غير مسجل')}</span><span class="status">العمر: ${profileAge(s.birth)}</span></div>`;
 const photo=root.querySelector('.file-photo-editor');
 if(photo){
  const panel=photo.closest('.panel'),dialog=document.createElement('dialog');dialog.id='profile-photo-dialog';
  photo.querySelector('summary').remove();dialog.innerHTML='<div class="dialog-head"><h2>صورة الطالب</h2><button type="button" class="quiet" id="profile-photo-close" aria-label="إغلاق">✕</button></div>'+photo.innerHTML;
  panel.replaceWith(dialog);
  hero.insertAdjacentHTML('beforeend',`<button type="button" class="photo-corner secondary" id="open-profile-photo"><span class="camera-square">📷</span> ${studentPortraits.get(s.id)?.data?'تغيير / حذف':'إضافة'}</button>`);
 }
 const form=root.querySelector('#profile-edit-child');
 if(form){
  const panel=form.closest('details'),dialog=document.createElement('dialog');dialog.id='profile-edit-dialog';
  dialog.innerHTML='<div class="dialog-head"><h2>تعديل بيانات الطالب</h2><button type="button" class="quiet" id="profile-edit-close" aria-label="إغلاق">✕</button></div>'+form.outerHTML;
  panel.replaceWith(dialog);dialog.insertAdjacentHTML('beforebegin','<button type="button" class="secondary profile-official-edit" id="open-profile-edit">✏️ تعديل بيانات الطالب</button>');
 }
 const archive=[...root.querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent.includes('إدارة وأرشفة'));
 if(archive){archive.querySelectorAll('[data-record-mode="edit"]').forEach(b=>b.remove());const actions=archive.querySelector('.body-space');archive.replaceWith(actions);}
 return template.innerHTML;
};
const windowBind=bind;
bind=function(){
 windowBind();
 for(const [name,close] of [['photo','profile-photo-close'],['edit','profile-edit-close']]){
  const button=$('#open-profile-'+name),dialog=$('#profile-'+name+'-dialog');
  if(button&&dialog)button.onclick=()=>{dialog.showModal();protectEditWindow(dialog,[close]);};
 }
};
const windowRecord=openRecord;
openRecord=function(...args){windowRecord(...args);const d=$('#record-dialog');if(d.open)protectEditWindow(d,['record-close','record-back']);};
const windowAccount=demoEditUser;
demoEditUser=function(...args){windowAccount(...args);protectEditWindow($('#record-dialog'),['demo-account-close']);};

const windowStudentForm=studentForm;
studentForm=function(){return windowStudentForm().replace('<label>طريقة الرسوم<select name="mode" id="fee-mode"><option value="none">بلا دفعة</option><option value="pay">دفع</option><option value="exempt">معفي</option></select></label>','<select name="mode" id="fee-mode" hidden aria-label="طريقة الرسوم"><option value="pay">دفع</option><option value="exempt">معفي</option><option value="none">بلا دفعة</option></select><div class="fee-mode-buttons"><button type="button" class="primary" data-fee-mode="pay">دفع</button><button type="button" class="secondary" data-fee-mode="exempt">معفي</button></div>').replace('name="registration">','name="registration" checked>').replace('name="gilet">','name="gilet" checked>');};
const windowStudentBind=bindStudentForm;
bindStudentForm=function(){
 windowStudentBind();const mode=$('#fee-mode');
 const sync=()=>{document.querySelectorAll('[data-fee-mode]').forEach(b=>b.className=b.dataset.feeMode===mode.value?'primary':'secondary');if(mode.value==='pay')$('#fee-note').textContent='يمكن حفظ صفر؛ الرسوم المحددة تبقى دينًا، وتستحق الشهرية عند اكتمال كل شهر من تاريخ بدء الاشتراك.';};
 document.querySelectorAll('[data-fee-mode]').forEach(b=>b.onclick=()=>{mode.value=b.dataset.feeMode;mode.dispatchEvent(new Event('change',{bubbles:true}));sync();});mode.addEventListener('change',sync);$('#student-form').addEventListener('input',sync);$('#student-form').addEventListener('change',sync);sync();
};
const windowRender=render;
render=function(){windowRender();const mode=$('#fee-mode');if(mode){document.querySelectorAll('[data-fee-mode]').forEach(b=>{if(![...mode.options].some(o=>o.value===b.dataset.feeMode))b.remove();});mode.dispatchEvent(new Event('change',{bubbles:true}));}};
const windowAccountProjection=account;
account=function(s){const a=windowAccountProjection(s);if(s.dueAtEnd&&!s.exempt&&!s.cancelled){const start=new Date(s.start+'T00:00:00'),now=new Date(today+'T00:00:00');let months=(now.getFullYear()-start.getFullYear())*12+now.getMonth()-start.getMonth();const boundary=new Date(start);boundary.setMonth(start.getMonth()+months,1);boundary.setDate(Math.min(start.getDate(),new Date(boundary.getFullYear(),boundary.getMonth()+1,0).getDate()));if(now<boundary)months--;const fees=Math.max(0,s.registration-total(a.rs,'registration'))+Math.max(0,s.gilet-total(a.rs,'gilet'));a.due=fees+Math.max(0,Math.max(0,months)*3000-a.monthPaid);}return a;};
