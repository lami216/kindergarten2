/* Read-only collection follow-up; the server owns eligibility and balances. */
'use strict';
const followupPrefix='followup.';
const FU=(key,values)=>I18N.tr(followupPrefix+key,values);
let followupData=null,followupLoading=false,followupError='',followupSequence=0;
let followupQuery='',followupDepartment='',followupTab='all',followupPage=1,followupOnScreen=false;
let followupMidnightTimer=null;
const followupActive=()=>page==='payments'&&financeTab==='followup';
const followupAllowed=()=>!!liveSession&&demoCan('receipts');
function invalidateFollowup(){if(followupMidnightTimer!==null)clearTimeout(followupMidnightTimer);followupMidnightTimer=null;followupSequence++;followupData=null;followupLoading=false;followupError='';}
function scheduleFollowupMidnight(){
 if(followupMidnightTimer!==null)clearTimeout(followupMidnightTimer);followupMidnightTimer=null;
 if(!followupData||!followupActive()||!followupAllowed())return;
 // Nouakchott's business day is UTC. Use the server's date; the browser's
 // local time zone must never bring a reminder forward or create any debt.
 const next=Date.parse(followupData.today+'T00:00:00Z')+86400000;
 if(!Number.isFinite(next))return;
 const delay=Math.max(60000,Math.min(86400000,next-Date.now()+1000));
 const version=followupSequence,identity=liveSession;
 followupMidnightTimer=setTimeout(()=>{
  followupMidnightTimer=null;
  if(version!==followupSequence||liveSession!==identity||!followupActive()||!followupAllowed()||document.visibilityState==='hidden')return;
  invalidateFollowup();loadFollowup();
 },delay);
}
function followupSearch(row){
 const term=searchText(followupQuery);if(!term)return true;
 const words=[row.name,row.father,row.mother,row.father_phone,row.mother_phone];
 const digits=term.replace(/[\s()+.\-]/g,'');
 return words.some(value=>searchText(value).includes(term))||(/^\d+$/.test(digits)&&[row.father_phone,row.mother_phone].some(value=>searchText(value).replace(/\D/g,'').includes(digits)));
}
function followupFiltered(){return (followupData?.items||[]).filter(row=>followupSearch(row)&&(!followupDepartment||String(row.department_id??'none')===followupDepartment));}
function followupRows(){return followupFiltered().filter(row=>followupTab==='all'||row.status===followupTab);}
function followupMoney(value){return FU('money',{value:money(Number(value||0))});}
function followupDate(value){return value?esc(I18N.date(value)):'—';}
function followupSummary(){
 const due=followupFiltered().filter(row=>row.status==='due');
 return `<div class="followup-metric"><span>${FU('dueStudents')}</span><strong>${I18N.number(due.length)}</strong></div><div class="followup-metric"><span>${FU('dueTotal')}</span><strong>${followupMoney(due.reduce((sum,row)=>sum+Number(row.due_total||0),0))}</strong></div>`;
}
function followupContacts(row){
 const parents=[[row.father,row.father_phone],[row.mother,row.mother_phone]].filter(([name,phone])=>name||phone);
 return parents.length?`<div class="followup-contacts">${parents.map(([name,phone])=>`<span>${esc(name||'')}${name&&phone?' · ':''}${phone?`<bdi dir="ltr">${esc(phone)}</bdi>`:''}</span>`).join('')}</div>`:'';
}
function followupCard(row){
 const due=row.status==='due',amount=due?row.due_total:row.upcoming?.remaining;
 return `<article class="followup-card" data-followup-student="${esc(row.id)}"><div class="followup-person">${studentAvatar({id:row.id,name:row.name},'avatar',row.photo)}<strong>${esc(row.name)}</strong></div><div class="followup-balance"><strong>${followupMoney(amount)}</strong><small class="${due?'followup-due':'followup-early'}">${due?FU('due'):I18N.tr(followupPrefix+'dueOn',{date:followupDate(row.upcoming?.due_date)})}</small></div><div class="followup-actions"><button type="button" class="link-button" data-followup-details="${esc(row.id)}">${FU('breakdown')} <span aria-hidden="true">${I18N.lang==='ar'?'‹':'›'}</span></button>${row.can_profile?`<button type="button" class="secondary small" data-followup-profile="${esc(row.id)}">${FU('profile')}</button>`:''}${row.can_pay?`<button type="button" class="secondary small" data-followup-pay="${esc(row.id)}">${FU('pay')}</button>`:''}</div></article>`;
}
function followupDetails(id){
 const row=followupData?.items.find(item=>String(item.id)===String(id));if(!row)return;
 const fields=[[FU('department'),row.department||FU('noDepartment')],[FU('currentDebt'),followupMoney(row.due_total)],[FU('monthlyDebt'),followupMoney(row.due_monthly)],[FU('feesDebt'),followupMoney(row.due_fees)]];
 if(row.earliest_due)fields.push([FU('dueSinceLabel'),followupDate(row.earliest_due)]);
 if(row.upcoming)fields.push([FU('nextInstalment'),followupMoney(row.upcoming.remaining)],[FU('dueDate'),followupDate(row.upcoming.due_date)]);
 fields.push([FU('reminderAppears'),followupDate(row.reminder_on)]);
 openProtected(FU('detailsTitle',{name:row.name}),`<div class="followup-details">${fileFields(fields)}${followupContacts(row)}${row.status==='upcoming'?`<p class="notice-box">${FU('notDebtYet')}</p>`:''}</div>`);
}
function followupResults(){
 const rows=followupRows(),pages=Math.max(1,Math.ceil(rows.length/20));followupPage=Math.max(1,Math.min(followupPage,pages));
 if(!rows.length)return `<div class="empty followup-empty"><span aria-hidden="true">✓</span><h3>${FU(followupQuery||followupDepartment?'noMatches':'emptyTitle')}</h3><p>${FU(followupQuery||followupDepartment?'changeSearch':'emptyHint')}</p></div>`;
 return `<div class="followup-result-caption"><span>${I18N.tr(followupPrefix+'studentsCount',{count:I18N.number(rows.length)})}</span><small>${FU('amountsCurrent')}</small></div><div class="followup-list">${rows.slice((followupPage-1)*20,followupPage*20).map(followupCard).join('')}</div><div class="pager followup-pager"><button type="button" class="secondary" data-followup-page="-1" ${followupPage===1?'disabled':''}>${FU('previous')}</button><span>${I18N.number(followupPage)} / ${I18N.number(pages)}</span><button type="button" class="secondary" data-followup-page="1" ${followupPage===pages?'disabled':''}>${FU('next')}</button></div>`;
}
function followupRepaint(){
 const summary=$('#followup-summary'),results=$('#followup-results');
 if(summary)summary.innerHTML=followupSummary();if(results)results.innerHTML=followupResults();
 const rows=followupFiltered();
 document.querySelectorAll('[data-followup-tab]').forEach(button=>{
  const kind=button.dataset.followupTab;button.classList.toggle('selected',kind===followupTab);button.setAttribute('aria-selected',String(kind===followupTab));button.tabIndex=kind===followupTab?0:-1;
  const count=button.querySelector('span');if(count)count.textContent=I18N.number(kind==='all'?rows.length:rows.filter(row=>row.status===kind).length);
 });
}
function followupBody(){
 if(followupLoading)return `<section class="panel followup-loading" role="status">${FU('loading')}</section>`;
 if(followupError)return `<section class="panel"><p class="error" role="alert">${esc(followupError)}</p><button type="button" class="secondary" data-followup-refresh>${FU('retry')}</button></section>`;
 if(!followupData)return '';
 const names=new Map();followupData.items.forEach(row=>names.set(String(row.department_id??'none'),row.department||FU('noDepartment')));
 if(followupDepartment&&!names.has(followupDepartment))followupDepartment='';
 return `<section class="panel followup-panel"><div class="followup-toolbar"><div class="followup-summary" id="followup-summary">${followupSummary()}</div><div class="followup-controls">${followupData.settings.editable?`<button type="button" class="secondary small" id="followup-settings">⚙ ${FU('settings')} · ${I18N.number(followupData.settings.day)}</button>`:''}<button type="button" class="secondary small" data-followup-refresh aria-label="${FU('refresh')}" title="${FU('refresh')}">↻</button></div></div><div class="followup-tools"><div class="followup-tabs" role="tablist" aria-label="${FU('show')}">${['all','due','upcoming'].map(kind=>`<button type="button" role="tab" class="${followupTab===kind?'selected':''}" aria-selected="${kind===followupTab}" tabindex="${kind===followupTab?0:-1}" data-followup-tab="${kind}">${FU(kind)} <span>${I18N.number(kind==='all'?followupFiltered().length:followupFiltered().filter(row=>row.status===kind).length)}</span></button>`).join('')}</div><input type="search" id="followup-search" aria-label="${FU('search')}" maxlength="120" value="${esc(followupQuery)}" placeholder="${FU('searchHint')}" autocomplete="off"><select id="followup-department" aria-label="${FU('department')}"><option value="">${FU('allDepartments')}</option>${[...names].sort((a,b)=>a[1].localeCompare(b[1],I18N.lang)).map(([id,name])=>`<option value="${esc(id)}" ${followupDepartment===id?'selected':''}>${esc(name)}</option>`).join('')}</select></div><div id="followup-results" aria-live="polite">${followupResults()}</div></section>`;
}
function followupPageHTML(){return `<div class="followup-page" id="followup-output">${followupBody()}</div>`;}
const followupPaymentPage=paymentPage;
paymentPage=function(){
 const template=document.createElement('template');template.innerHTML=followupPaymentPage();
 const choices=template.content.querySelector('.choices');
 if(!choices||!followupAllowed())return template.innerHTML;
 choices.classList.add('finance-choices');
 choices.insertAdjacentHTML('beforeend',`<button class="choice ${financeTab==='followup'?'active':''}" data-finance="followup">${FU('title')}</button>`);
 if(financeTab==='followup'){
  while(choices.nextElementSibling)choices.nextElementSibling.remove();
  choices.insertAdjacentHTML('afterend',followupPageHTML());
  template.content.querySelector('.page-heading p')?.remove();
 }
 return template.innerHTML;
};
async function loadFollowup(){
 if(!followupAllowed()||!followupActive()||followupLoading)return;
 const identity=liveSession,version=++followupSequence;followupLoading=true;followupError='';
 const block=$('#followup-output');if(block)block.innerHTML=followupBody();
 document.querySelector('[data-followup-refresh]')?.setAttribute('disabled','');
 try{
  const data=await liveCall('followup.read',{});
  if(version!==followupSequence||liveSession!==identity||!followupActive()||!followupAllowed())return;
  followupData=data;followupLoading=false;followupError='';render();scheduleFollowupMidnight();
 }catch(error){
  if(version!==followupSequence||liveSession!==identity||!followupActive())return;
  followupLoading=false;followupError=error.message;render();
 }
}
function followupSettingsWindow(){
 const settings=followupData?.settings;if(!settings?.editable)return;
 openProtected(FU('settings'),`<form id="followup-settings-form" data-revision="${esc(settings.revision)}"><label>${FU('reminderDay')}<input name="day" type="number" min="1" max="31" step="1" value="${settings.day}" required inputmode="numeric"></label><p class="muted followup-settings-hint">${FU('settingsHint')}</p>${confirmation()}</form>`);
 $('#followup-settings-form [name=reason]').maxLength=500;
}
const followupRender=render;
render=function(){
 const entering=followupActive()&&!followupOnScreen;
 if(!followupActive()&&followupOnScreen)invalidateFollowup();
 if(entering){invalidateFollowup();followupPage=1;}
 followupOnScreen=followupActive();
 followupRender();
 $('#nav-followup')?.remove();$('#home-followup')?.remove();
 if(followupActive()&&followupAllowed()&&!followupData&&!followupLoading&&!followupError)queueMicrotask(()=>{if(followupActive())loadFollowup();});
};
const followupLoad=liveLoad;
liveLoad=async function(...args){const result=await followupLoad(...args);invalidateFollowup();return result;};
const followupSubmit=liveSubmit;
liveSubmit=async function(form){
 if(form.id!=='followup-settings-form')return followupSubmit(form);
 const data=new FormData(form);
 return liveSaved('followup.settings',{day:String(data.get('day')||''),revision:form.dataset.revision,reason:String(data.get('reason')||''),confirmed:data.has('confirmed')},form);
};
const followupLogin=liveLoginScreen;
liveLoginScreen=function(){invalidateFollowup();followupQuery='';followupDepartment='';followupTab='all';followupPage=1;followupOnScreen=false;$('#nav-followup')?.remove();followupLogin();};
document.addEventListener('input',event=>{if(event.target.id==='followup-search'){followupQuery=event.target.value;followupPage=1;followupRepaint();}});
document.addEventListener('change',event=>{if(event.target.id==='followup-department'){followupDepartment=event.target.value;followupPage=1;followupRepaint();}});
document.addEventListener('click',async event=>{
 const button=event.target.closest('button');if(!button||!button.matches('[data-followup-refresh],[data-followup-tab],[data-followup-page],[data-followup-profile],[data-followup-pay],[data-followup-details],#followup-settings'))return;
 event.preventDefault();event.stopImmediatePropagation();if(!followupAllowed())return;
 if(button.hasAttribute('data-followup-refresh')){invalidateFollowup();loadFollowup();return;}
 if(button.dataset.followupDetails){followupDetails(button.dataset.followupDetails);return;}
 if(button.id==='followup-settings'){followupSettingsWindow();return;}
 if(button.dataset.followupTab){followupTab=button.dataset.followupTab;followupPage=1;followupRepaint();return;}
 if(button.dataset.followupPage){followupPage+=Number(button.dataset.followupPage);followupRepaint();$('#followup-results')?.scrollIntoView({block:'start'});return;}
 const id=button.dataset.followupProfile||button.dataset.followupPay,row=followupData?.items.find(item=>String(item.id)===id);if(!row)return;
 if(!button.dataset.followupProfile&&!button.dataset.followupPay)return;
 button.disabled=true;
 try{
  const current=await liveCall('session');
  liveSession=current;demoActor=liveUser(current.user);
  await liveLoad();
  const mayProfile=current.user.is_admin||current.user.permissions.includes('students.view');
  const mayPay=current.user.is_admin||current.user.permissions.includes('payments.create');
  if(!followupAllowed()||button.dataset.followupProfile&&!mayProfile||button.dataset.followupPay&&!mayPay){if(followupActive())render();toast(FU('changedStudent'),'error');return;}
  const student=students.find(item=>item.id===row.id);
  if(!student||student.cancelled){if(followupActive())render();toast(FU('changedStudent'),'error');return;}
  if(button.dataset.followupProfile&&row.can_profile){page='students';profileId=row.id;render();pageTop();return;}
  if(button.dataset.followupPay&&row.can_pay){
   if(student.exempt){if(followupActive())render();toast(FU('changedStudent'),'error');return;}
   receiptChild=row.id;financeTab='payment';navigate('payments');
   // This is a newly opened, empty payment form. Refresh its automatic cash
   // date after midnight without touching any existing operator draft.
   const input=$('#pay-date'),fresh=liveData?.today;
   if(input&&/^\d{4}-\d{2}-\d{2}$/.test(fresh||'')){input.setAttribute('max',fresh);input.setAttribute('value',fresh);input.value=fresh;}
  }
 }catch(error){toast(error.message,'error');}finally{if(button.isConnected)button.disabled=false;}
},true);
document.addEventListener('keydown',event=>{
 const button=event.target.closest('.followup-tabs [role=tab]');if(!button)return;
 const tabs=[...document.querySelectorAll('.followup-tabs [role=tab]')],index=tabs.indexOf(button),direction=I18N.lang==='ar'?-1:1;let next;
 if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else if(event.key==='ArrowRight')next=(index+direction+tabs.length)%tabs.length;else if(event.key==='ArrowLeft')next=(index-direction+tabs.length)%tabs.length;else return;
 event.preventDefault();tabs[next].click();tabs[next].focus();
});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&followupActive()&&followupAllowed()&&!followupLoading){invalidateFollowup();loadFollowup();}});
if(liveSession&&liveData)render();
