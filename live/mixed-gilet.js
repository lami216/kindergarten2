/* One item cancellation; retained receipt allocations are copied by the server. */
'use strict';
const MI=k=>I18N.tr(`mixedGilet.${k}`);
recordNames.monthly_gilet_cancellations=MI('history');
Object.assign(historyFields,{receipt_id:MI('original'),replacement_id:MI('replacement'),cancelled_at:MI('time')});
const mixedReceiptScreen=receiptScreen;
receiptScreen=function(){
 const t=document.createElement('template');t.innerHTML=mixedReceiptScreen();
 const r=receipts.find(x=>x.id===receiptPageId),panel=t.content.querySelector('#receipt-page');
 if(!r||!panel)return t.innerHTML;
 const can=demoCan('receipts','cancel')&&(demoActor.admin||liveSession.user.permissions.includes('accounts.delete'));
 if(!r.cancelled&&r.gilet>0&&r.gilet<r.amount){
  if(r.gilet_item_eligible&&can)panel.querySelector('.actions').insertAdjacentHTML('beforeend',`<button class="secondary danger" data-cancel-gilet-item="${r.id}">${MI('action')}</button>`);
  else panel.insertAdjacentHTML('beforeend',`<p class="muted body-space">${MI(can?'unsupported':'permission')}</p>`);
 }
 const links=[];
 if(r.corrects_id)links.push(`<button class="secondary small" data-receipt-chain="${r.corrects_id}">${MI('original')} #${r.corrects_id}</button>`);
 for(const child of receipts.filter(x=>x.corrects_id===r.id))links.push(`<button class="secondary small" data-receipt-chain="${child.id}">${MI('replacement')} #${child.id}</button>`);
 if(links.length)panel.insertAdjacentHTML('beforeend',`<div class="actions body-space">${links.join('')}</div>`);
 if(r.gilet_cancellation)panel.insertAdjacentHTML('beforeend',`<p class="notice-box body-space">${I18N.tr('mixedGilet.trace',{amount:money(r.gilet_cancellation.amount)})}</p>`);
 return t.innerHTML;
};
async function cancelGiletItemWindow(id){
 const p=await liveCall('receipts.gilet.preview',{id});
 if(!p.eligible)throw Error(I18N.message(p.reason));
 if(!p.can_cancel)throw Error(MI('permission'));
 openProtected(MI('action'),`<form id="mixed-gilet-cancel-form" data-id="${id}" data-revision="${p.revision}"><p><strong>${esc(p.name)}</strong> · ${MI('original')} #${id}</p><div class="summary-detail body-space">${detailLine(MI('removed'),money(p.gilet)+' MRO')}${detailLine(MI('registration'),money(p.registration)+' MRO')}${detailLine(MI('monthly'),money(p.monthly)+' MRO')}${detailLine(MI('remaining'),money(p.remaining)+' MRO')}</div><p class="notice-box">${MI('effect')}</p>${confirmation()}</form>`);
 $('#mixed-gilet-cancel-form button.primary').textContent=MI('confirm');
}
const mixedGiletSubmit=liveSubmit;
liveSubmit=async function(form){
 if(form.id!=='mixed-gilet-cancel-form')return mixedGiletSubmit(form);
 const d=new FormData(form);
 const result=await liveSaved('receipts.gilet.cancel',{id:Number(form.dataset.id),revision:Number(form.dataset.revision),reason:String(d.get('reason')||''),confirmed:d.has('confirmed')},form);
 openReceipt(result.id);return result;
};
document.addEventListener('click',event=>{
 const b=event.target.closest('button');if(!b)return;
 if(b.dataset.cancelGiletItem){event.preventDefault();cancelGiletItemWindow(Number(b.dataset.cancelGiletItem)).catch(error=>toast(error.message,'error'));}
 if(b.dataset.receiptChain){event.preventDefault();openReceipt(Number(b.dataset.receiptChain));}
});
if(liveSession&&liveData)render();
