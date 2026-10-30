/* The Pages interaction model uses the same protected-window workflow. */
function formSignature(dialog){
 return JSON.stringify([...dialog.querySelectorAll('input:not([data-date-part]),select:not([data-date-part]),textarea')].map(e=>[
  e.name||e.id,e.type==='checkbox'?e.checked:e.type==='file'?[...e.files].map(f=>[f.name,f.size,f.lastModified]):e.dataset.dateDraft??e.value
 ]));
}
function protectEditWindow(dialog,closeIds=[]){
 const clearDiscard=()=>dialog.querySelectorAll('.discard-box').forEach(box=>box.remove());
 clearDiscard();dialog.onclose=()=>{if(!dialog.open)clearDiscard();};
 const initial=formSignature(dialog);
 const close=()=>{clearDiscard();dialog.close();if(dialog.id.startsWith('profile-')||dialog.id==='transfer-dialog')render();};
 const requestClose=()=>{
  if(formSignature(dialog)===initial){close();return;}
  if(dialog.querySelector('.discard-box'))return;
  const box=document.createElement('div');box.className='discard-box';box.setAttribute('role','alert');
  box.innerHTML=`<p>${I18N.tr("ui.c2841c04da4f")}</p><div class="actions"><button type="button" class="danger" data-discard>${I18N.tr("ui.dc80cb7603ef")}</button><button type="button" class="secondary" data-keep>${I18N.tr("ui.30dc28305899")}</button></div>`;
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
 description.outerHTML=`<div class="file-tags"><span class="status ${s.gender==='ذكر'?'boy':s.gender==='أنثى'?'girl':''}">${esc(I18N.enumLabel(s.gender)||`${I18N.tr("ui.fdb8ba844e96")}`)}</span><span class="status">${I18N.tr("ui.00902581f841",{p0:profileAge(s.birth)})}</span></div>`;
 const photo=root.querySelector('.file-photo-editor');
 if(photo){
  const panel=photo.closest('.panel'),dialog=document.createElement('dialog');dialog.id='profile-photo-dialog';
  photo.querySelector('summary').remove();dialog.innerHTML=`<div class="dialog-head"><h2>${I18N.tr("ui.5af55b286bcf")}</h2><button type="button" class="quiet" id="profile-photo-close" aria-label="${I18N.tr("ui.ca90c297b099")}">✕</button></div>${photo.innerHTML}`;
  panel.replaceWith(dialog);
  hero.insertAdjacentHTML('beforeend',`<button type="button" class="photo-corner secondary" id="open-profile-photo"><span class="camera-square">📷</span> ${studentPortraits.get(s.id)?.data?`${I18N.tr("ui.4c5811fc101d")}`:`${I18N.tr("ui.d52453ac627d")}`}</button>`);
 }
 const form=root.querySelector('#profile-edit-child');
 if(form){
  const panel=form.closest('details'),dialog=document.createElement('dialog');dialog.id='profile-edit-dialog';
  dialog.innerHTML=`<div class="dialog-head"><h2>${I18N.tr("ui.85868023dbc3")}</h2><button type="button" class="quiet" id="profile-edit-close" aria-label="${I18N.tr("ui.ca90c297b099")}">✕</button></div>${form.outerHTML}`;
  panel.replaceWith(dialog);dialog.insertAdjacentHTML('beforebegin',`<button type="button" class="secondary profile-official-edit" id="open-profile-edit">${I18N.tr("ui.6ae5cc43e3c2")}</button>`);
 }
 const archive=[...root.querySelectorAll('details')].find(d=>d.querySelector('summary')?.textContent.includes(`${I18N.tr("ui.5e2a40e97c93")}`));
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
studentForm=function(){return windowStudentForm().replace(`<label>${I18N.tr("ui.53eac27f0c0e")}<select name="mode" id="fee-mode"><option value="none">${I18N.tr("ui.d959dbb6c737")}</option><option value="pay">${I18N.tr("ui.5e1b515f1b13")}</option><option value="exempt">${I18N.tr("ui.a3ae7c221c0f")}</option></select></label>`,`<select name="mode" id="fee-mode" hidden aria-label="${I18N.tr("ui.53eac27f0c0e")}"><option value="pay">${I18N.tr("ui.5e1b515f1b13")}</option><option value="exempt">${I18N.tr("ui.a3ae7c221c0f")}</option><option value="none">${I18N.tr("ui.d959dbb6c737")}</option></select><div class="fee-mode-buttons"><button type="button" class="primary" data-fee-mode="pay">${I18N.tr("ui.5e1b515f1b13")}</button><button type="button" class="secondary" data-fee-mode="exempt">${I18N.tr("ui.a3ae7c221c0f")}</button></div>`).replace('name="registration">','name="registration" checked>').replace('name="gilet">','name="gilet" checked>');};
const windowStudentBind=bindStudentForm;
bindStudentForm=function(){
 windowStudentBind();const mode=$('#fee-mode');
 const sync=()=>{document.querySelectorAll('[data-fee-mode]').forEach(b=>b.className=b.dataset.feeMode===mode.value?'primary':'secondary');if(mode.value==='pay')$('#fee-note').textContent=`${I18N.tr("ui.a186f1b7b199")}`;};
 document.querySelectorAll('[data-fee-mode]').forEach(b=>b.onclick=()=>{mode.value=b.dataset.feeMode;mode.dispatchEvent(new Event('change',{bubbles:true}));sync();});mode.addEventListener('change',sync);$('#student-form').addEventListener('input',sync);$('#student-form').addEventListener('change',sync);sync();
};
const windowRender=render;
render=function(){windowRender();const mode=$('#fee-mode');if(mode){document.querySelectorAll('[data-fee-mode]').forEach(b=>{if(![...mode.options].some(o=>o.value===b.dataset.feeMode))b.remove();});mode.dispatchEvent(new Event('change',{bubbles:true}));}};
const windowAccountProjection=account;
account=function(s){const a=windowAccountProjection(s);if(s.dueAtEnd&&!s.exempt&&!s.cancelled){const start=new Date(s.start+'T00:00:00'),now=new Date(today+'T00:00:00');let months=(now.getFullYear()-start.getFullYear())*12+now.getMonth()-start.getMonth();const boundary=new Date(start);boundary.setMonth(start.getMonth()+months,1);boundary.setDate(Math.min(start.getDate(),new Date(boundary.getFullYear(),boundary.getMonth()+1,0).getDate()));if(now<boundary)months--;const fees=Math.max(0,s.registration-total(a.rs,'registration'))+Math.max(0,s.gilet-total(a.rs,'gilet'));a.due=fees+Math.max(0,Math.max(0,months)*3000-a.monthPaid);}return a;};

const windowRegistration=registrationPage;
registrationPage=function(){const t=document.createElement('template');t.innerHTML=windowRegistration();const f=t.content.querySelector('#transfer-form');if(f){const d=document.createElement('dialog');d.id='transfer-dialog';d.innerHTML=`<div class="dialog-head"><h2>${I18N.tr("ui.21af9417dbb0")}</h2><button class="quiet" type="button" id="transfer-close" aria-label="${I18N.tr("ui.ca90c297b099")}">✕</button></div>${f.outerHTML}`;f.replaceWith(d);d.insertAdjacentHTML('beforebegin',`<button type="button" class="secondary profile-official-edit" id="open-transfer">${I18N.tr("ui.21af9417dbb0")}</button>`);}return t.innerHTML;};
const transferWindowBind=bind;
bind=function(){transferWindowBind();const b=$('#open-transfer');if(b)b.onclick=()=>{const d=$('#transfer-dialog');d.showModal();protectEditWindow(d,['transfer-close']);};};

const windowPaymentBody=paymentBody;
paymentBody=function(s){const a=account(s);let fees='';if(!s.exempt&&!s.cancelled&&demoCan('receipts','create'))for(const [kind,label] of [['registration',`${I18N.tr("ui.6a8d48082bb7")}`],['gilet',`${I18N.tr("ui.c0a240e22598")}`]]){const due=window.LIVE_APP?s.account[kind+'_due']:Math.max(0,s[kind]-total(a.rs,kind));if(due)fees+=`<button type="button" class="secondary" data-collect-fee="${kind}" data-student="${esc(s.id)}">${I18N.tr("ui.57ff82ae95d2",{p0:label,p1:money(due)})}</button>`;}return(fees?'<div class="actions body-space">'+fees+'</div>':'')+windowPaymentBody(s);};
const feeWindowBind=bindPayment;
bindPayment=function(){feeWindowBind();document.querySelectorAll('[data-collect-fee]').forEach(b=>b.onclick=()=>{
 const s=students.find(s=>s.id===(window.LIVE_APP?b.dataset.student:+b.dataset.student)),kind=b.dataset.collectFee,label=kind==='registration'?`${I18N.tr("ui.6a8d48082bb7")}`:`${I18N.tr("ui.c0a240e22598")}`,due=window.LIVE_APP?s.account[kind+'_due']:Math.max(0,s[kind]-total(account(s).rs,kind)),snapshot=JSON.stringify(account(s).rs);
 const dialog=$('#record-dialog');$('#record-content').innerHTML=`<div class="dialog-head"><h2>${I18N.tr("ui.5c226064f36b",{p0:label})}</h2><button type="button" class="quiet" id="fee-close" aria-label="${I18N.tr("ui.ca90c297b099")}">✕</button></div><form id="fee-collect-form"><label>${I18N.tr("ui.1de51d2cdd19")}<input type="date" name="date" value="${today}" max="${today}" required></label><p>${I18N.tr("ui.85be68ca023f")} <strong>${I18N.tr("ui.256481ee805d",{p0:money(due)})}</strong></p><p class="muted">${I18N.tr("ui.4c3a88400cfb")}</p><label class="check-row"><input type="checkbox" name="agree" required>${I18N.tr("ui.5ac123292c50")}</label><p class="error" id="fee-collect-error" role="alert"></p><button class="primary">${I18N.tr("ui.50a471f10e8f")}</button></form>`;
 dialog.showModal();protectEditWindow(dialog,['fee-close']);$('#fee-collect-form').onsubmit=e=>{e.preventDefault();if(!e.target.reportValidity())return;if(!demoCan('receipts','create')||s.cancelled||s.exempt||JSON.stringify(account(s).rs)!==snapshot){$('#fee-collect-error').textContent=`${I18N.tr("ui.b3054aeeed16")}`;return;}const r={id:Math.max(100,...receipts.map(r=>r.id))+1,student:s.id,date:new FormData(e.target).get('date'),amount:due,registration:kind==='registration'?due:0,gilet:kind==='gilet'?due:0,monthly:0};receipts.push(r);logChange('receipts',r.id,'created',null,r,`${I18N.tr("ui.5c226064f36b",{p0:label})}`);dialog.close();render();toast(`${I18N.tr("ui.6709b6af218b",{p0:label})}`);};
});};
