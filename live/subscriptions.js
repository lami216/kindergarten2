/* Subscription dates share the official student editor and account design. */
'use strict';
const ST=k=>I18N.tr(`subscription.${k}`);
const subscriptionStudentForm=studentForm;
studentForm=function(){
 const t=document.createElement('template');t.innerHTML=subscriptionStudentForm();
 t.content.querySelector('.form-grid').insertAdjacentHTML('beforeend',`<label>${ST('start')}<input type="date" name="start_date" id="student-subscription-start" value="${today}" min="1990-01-01" max="${today}" required><small class="muted">${ST('startHint')}</small></label>`);
 return t.innerHTML;
};
function subscriptionDetails(s){
 const a=s.account,day=v=>v?I18N.date(v):'—';
 const partial=a.partial_period?detailLine(ST('partialPaid'),money(a.partial_period.paid)) + detailLine(ST('partialRemaining'),money(a.partial_period.remaining)):'';
 const fees=Object.entries(a.fee_details||{}).map(([key,fee])=>`<div class="summary-line account-fee-row"><span>${ST(key)}</span><div><strong>${I18N.tr('subscription.feePaid',{paid:money(fee.paid),price:money(fee.price)})}</strong>${fee.waived?`<small>${I18N.tr('subscription.waived',{amount:money(fee.waived)})}</small>`:''}${fee.remaining?`<small>${ST('remaining')}: ${money(fee.remaining)}</small>`:''}</div></div>`).join('');
 return `<details class="file-account-details"><summary>${ST('details')}</summary>${fileFields([[ST('nextMonth'),day(a.next_unpaid)],[ST('nextDue'),day(a.next_due)]])}${partial}${fees}</details>`;
}
const subscriptionProfile=profile;
profile=function(){
 const s=students.find(x=>x.id===profileId),t=document.createElement('template');t.innerHTML=subscriptionProfile();
 if(!s)return t.innerHTML;
 const info=t.content.querySelector('.file-info .file-details');
 if(info&&s.registered_on)info.insertAdjacentHTML('beforeend',`<div><small>${ST('registrationDate')}</small><p>${esc(I18N.date(s.registered_on))}</p></div>`);
 const form=t.content.querySelector('#profile-edit-child'),edit=s.subscription_edit;
 if(form&&edit){
  form.dataset.accountRevision=edit.revision;form.dataset.ledgerRevision=edit.ledger_revision;form.dataset.subscriptionStart=edit.start;
  form.querySelector('.form-grid').insertAdjacentHTML('beforeend',`<label>${ST('start')}<input type="date" name="start_date" id="profile-registration-start" value="${esc(edit.start)}" min="1990-01-01" max="${today}" required><small class="muted">${ST('editHint')}</small></label>`);
 }
 const panel=t.content.querySelector('#profile-receipts')?.closest('section');
 if(panel&&s.account){
  panel.classList.add('file-account');panel.querySelector('.subscription-anchor-note')?.remove();
  const stats=panel.querySelector('.stats');stats.classList.add('file-account-stats');
  stats.insertAdjacentHTML('beforeend',stat('🗓️',ST('fullMonths'),I18N.number(s.account.full)) + stat('✅',ST('paidThrough'),s.account.paid_through?I18N.date(s.account.paid_through):'—'));
  stats.lastElementChild.classList.add('account-date');
  panel.querySelector('.actions').insertAdjacentHTML('beforebegin',subscriptionDetails(s));
 }
 return t.innerHTML;
};
if(liveSession&&liveData)render();
