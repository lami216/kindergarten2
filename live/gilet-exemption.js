/* Garment sales and explicit, noncash exemption use the existing live ledger. */
'use strict';
const GE=k=>I18N.tr(`gilet.${k}`), EX=k=>I18N.tr(`exemption.${k}`);
const garmentProfile=profile;
profile=function(){
 const s=students.find(x=>x.id===profileId),t=document.createElement('template');t.innerHTML=garmentProfile();
 if(!s||s.cancelled||!s.account)return t.innerHTML;
 const actions=t.content.querySelector('.file-account .actions');
 if(actions&&demoCan('receipts'))actions.insertAdjacentHTML('beforeend',`<button class="secondary" data-gilet="${esc(s.id)}">${GE(demoCan('receipts','create')?'sell':'purchases')}</button>`);
 if(!s.exempt&&(demoActor.admin||liveSession.user.permissions.includes('accounts.edit'))){
  const box=actions||t.content.querySelector('.file-hero .actions');
  box?.insertAdjacentHTML('beforeend',`<button class="secondary" data-exempt="${esc(s.id)}">${EX('action')}</button>`);
 }
 return t.innerHTML;
};
function exemptionNote(p){return I18N.tr('exemption.confirm',{amount:money(p.due)});}
async function garmentWindow(student){
 const p=await liveCall('gilet.preview',{student}),s=students.find(x=>x.id===student);
 openProtected(GE('purchases'),`<p class="muted">${esc(p.name)}</p>${p.purchases.map(x=>`<div class="list-card"><div><strong>${money(x.price)} MRO</strong><small>${GE(x.cancelled?'cancelled':x.delivered?'delivered':x.due?'unpaid':'unknown')}</small>${x.cancelled&&x.delivered?`<small>${GE('noReturn')}</small>`:''}</div><div class="actions">${x.receipt?`<button type="button" class="secondary small" data-gilet-receipt="${x.receipt}">${GE('receipt')}</button>`:''}${x.kind==='legacy'&&x.paid>=x.price&&x.price>0&&!x.delivered&&demoCan('receipts','edit')?`<button type="button" class="secondary small" data-gilet-deliver="${x.id}" data-student="${esc(student)}" data-ledger="${p.ledger_revision}">${GE('deliver')}</button>`:''}</div></div>`).join('')||`<p class="muted body-space">${GE('none')}</p>`}${demoCan('receipts','create')&&!s.paused?`<form id="gilet-sale-form" data-student="${esc(student)}" data-price="${p.price}" data-tariff="${p.tariff_revision}" class="body-space"><h3>${GE('sell')}</h3><p class="notice-box">${GE('one')} · <strong>${money(p.price)} MRO</strong></p><label>${GE('date')}<input type="date" name="date" value="${today}" min="1990-01-01" max="${today}" required></label><label class="check-row body-space"><input type="checkbox" name="confirmed" required>${GE('confirm')}</label><p class="error" role="alert"></p><button class="primary body-space" ${p.price>0?'':'disabled'}>${GE('submit')}</button>${p.price>0?'':`<p>${GE('setPrice')}</p>`}</form>`:''}`);
}
async function exemptionWindow(student){
 const p=await liveCall('exemption.preview',{student});
 openProtected(EX('action'),`<form id="exemption-form" data-student="${esc(student)}" data-revision="${p.revision}" data-ledger="${p.ledger_revision}" data-due="${p.due}"><p class="notice-box">${esc(exemptionNote(p))}</p>${p.can_waive?confirmation():`<p class="error">${EX('permission')}</p>`}</form>`);
}
const garmentToolEditor=toolEditor;
toolEditor=function(id,mode){
 garmentToolEditor(id,mode);
 const form=$('#tool-edit-form');if(form?.dataset.table!=='monthly_accounts'||mode!=='edit')return;
 const status=form.elements.status,original=status.value,button=form.querySelector('button.primary');
 status.addEventListener('change',async()=>{
  delete form.dataset.exemptionDue;delete form.dataset.exemptionLedger;form.querySelector('.exemption-confirm-note')?.remove();
  if(status.value!=='exempt'||original==='exempt'){button.disabled=false;return;}
  button.disabled=true;
  try{
   const p=await liveCall('exemption.preview',{student:String(id)});
   if(!form.isConnected||status.value!=='exempt')return;
   form.dataset.revision=p.revision;form.dataset.exemptionDue=p.due;form.dataset.exemptionLedger=p.ledger_revision;
   button.insertAdjacentHTML('beforebegin',`<p class="notice-box exemption-confirm-note">${esc(exemptionNote(p))}</p>`);
   button.disabled=!p.can_waive;if(!p.can_waive)liveError(form,Error(EX('permission')));
  }catch(e){if(form.isConnected)liveError(form,e);}
 });
};
const garmentSubmit=liveSubmit;
liveSubmit=async function(form){
 const d=new FormData(form),get=k=>String(d.get(k)||'');
 if(form.id==='gilet-sale-form'){
  const r=await liveSaved('gilet.sell',{student:form.dataset.student,price:Number(form.dataset.price),tariff_revision:form.dataset.tariff,date:get('date'),confirmed:d.has('confirmed')},form);
  openReceipt(r.id);return r;
 }
 if(form.id==='gilet-delivery-form')return liveSaved('gilet.deliver',{student:form.dataset.student,fee:Number(form.dataset.fee),ledger_revision:Number(form.dataset.ledger),reason:get('reason'),confirmed:d.has('confirmed')},form);
 if(form.id==='exemption-form')return liveSaved('exemption.apply',{student:form.dataset.student,revision:form.dataset.revision,ledger_revision:Number(form.dataset.ledger),due:Number(form.dataset.due),reason:get('reason'),confirmed:d.has('confirmed')},form);
 return garmentSubmit(form);
};
document.addEventListener('click',event=>{
 const b=event.target.closest('button');if(!b)return;
 if(b.dataset.gilet){event.preventDefault();garmentWindow(b.dataset.gilet).catch(e=>toast(e.message,'error'));}
 if(b.dataset.exempt){event.preventDefault();exemptionWindow(b.dataset.exempt).catch(e=>toast(e.message,'error'));}
 if(b.dataset.giletReceipt){$('#record-dialog').close();openReceipt(Number(b.dataset.giletReceipt));}
 if(b.dataset.giletDeliver){
  openProtected(GE('deliver'),`<form id="gilet-delivery-form" data-student="${esc(b.dataset.student)}" data-fee="${b.dataset.giletDeliver}" data-ledger="${b.dataset.ledger}"><p class="notice-box">${GE('deliveryOnly')}</p>${confirmation()}</form>`);
 }
});
if(liveSession&&liveData)render();
