/* Read-only collection follow-up; the server owns eligibility and balances. */
'use strict';
const followupPrefix='followup.';
const FU=(key,values)=>I18N.tr(followupPrefix+key,values);
let followupData=null,followupLoading=false,followupError='',followupSequence=0;
let followupQuery='',followupDepartment='',followupPage=1,followupOnScreen=false;
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
function followupItems(){return (followupData?.items||[]).filter(row=>row.status==='due'&&Number(row.due_total)>0);}
function followupFiltered(){return followupItems().filter(row=>followupSearch(row)&&(!followupDepartment||String(row.department_id??'none')===followupDepartment));}
function followupMoney(value){return FU('money',{value:money(Number(value||0))});}
function followupDate(value){return value?esc(I18N.date(value)):'—';}
function followupMonth(value){
 const match=/^(\d{4})-(\d{2})-\d{2}$/.exec(String(value||''));
 if(!match||Number(match[2])<1||Number(match[2])>12)return FU('unknownMonth');
 const monthKey='date.month.'+Number(match[2]);
 return I18N.tr(monthKey)+' '+match[1];
}
function followupSummary(){
 const due=followupFiltered();
 return `<div class="followup-metric"><span>${FU('dueStudents')}</span><strong>${I18N.number(due.length)}</strong></div><div class="followup-metric"><span>${FU('dueTotal')}</span><strong>${followupMoney(due.reduce((sum,row)=>sum+Number(row.due_total||0),0))}</strong></div>`;
}
function followupContacts(row){
 const parents=[[row.father,row.father_phone],[row.mother,row.mother_phone]].filter(([name,phone])=>name||phone);
 return parents.length?`<div class="followup-contacts">${parents.map(([name,phone])=>`<span>${esc(name||'')}${name&&phone?' · ':''}${phone?`<bdi dir="ltr">${esc(phone)}</bdi>`:''}</span>`).join('')}</div>`:'';
}
function followupCard(row){
 const periods=[...(row.due_periods||[])].sort((a,b)=>String(a.start).localeCompare(String(b.start))),first=periods[0];
 const month=first?followupMonth(first.start):'';
 const caption=first?`${esc(periods.length>1?FU('monthsSince',{month}):month)} · ${FU('due')}`:FU('feesDue');
 return `<article class="followup-card" data-followup-student="${esc(row.id)}"><div class="followup-person">${studentAvatar({id:row.id,name:row.name},'avatar',row.photo)}<strong>${esc(row.name)}</strong></div><div class="followup-balance"><strong>${followupMoney(row.due_total)}</strong><small class="followup-due">${caption}</small></div><div class="followup-actions"><button type="button" class="link-button" data-followup-details="${esc(row.id)}">${FU('breakdown')} <span aria-hidden="true">${I18N.lang==='ar'?'‹':'›'}</span></button>${row.can_profile?`<button type="button" class="secondary small" data-followup-profile="${esc(row.id)}">${FU('profile')}</button>`:''}${row.can_pay?`<button type="button" class="secondary small" data-followup-pay="${esc(row.id)}">${FU('pay')}</button>`:''}</div></article>`;
}
function followupPeriodDetails(row){
 const periods=row.due_periods||[];
 if(!periods.length)return '';
 const seen=new Set(),unique=periods.filter(period=>{
  const key=period.start+'|'+period.due_date;if(seen.has(key))return false;seen.add(key);return true;
 }).sort((a,b)=>String(a.start).localeCompare(String(b.start)));
 const cell='padding:8px 4px;text-align:start;vertical-align:top';
 return `<section class="body-space followup-period-details"><h3 style="font-size:14px;font-weight:500;margin:0 0 8px">${FU('unpaidMonths')}</h3><table style="width:100%;font-size:12px;table-layout:auto"><thead><tr>${['month','remaining','dueDate'].map(key=>`<th scope="col" style="${cell}">${FU(key)}</th>`).join('')}</tr></thead><tbody>${unique.map(period=>`<tr><td style="${cell}">${esc(followupMonth(period.start))}</td><td style="${cell}">${followupMoney(period.remaining)}</td><td style="${cell}"><bdi dir="ltr">${followupDate(period.due_date)}</bdi></td></tr>`).join('')}</tbody></table></section>`;
}
function followupDetails(id){
 const row=followupItems().find(item=>String(item.id)===String(id));if(!row)return;
 const fields=[[FU('department'),row.department||FU('noDepartment')],[FU('currentDebt'),followupMoney(row.due_total)],[FU('monthlyDebt'),followupMoney(row.due_monthly)],[FU('feesDebt'),followupMoney(row.due_fees)]];
 if(row.earliest_due)fields.push([FU('dueSinceLabel'),followupDate(row.earliest_due)]);
 fields.push([FU('lastPaidMonth'),row.last_paid_month?followupMonth(row.last_paid_month):FU('noPaidMonth')]);
 openProtected(FU('detailsTitle',{name:row.name}),`<div class="followup-details">${fileFields(fields)}${followupPeriodDetails(row)}${followupContacts(row)}</div>`);
}
function followupResults(){
 const rows=followupFiltered(),pages=Math.max(1,Math.ceil(rows.length/20));followupPage=Math.max(1,Math.min(followupPage,pages));
 if(!rows.length)return `<div class="empty followup-empty"><span aria-hidden="true">✓</span><h3>${FU(followupQuery||followupDepartment?'noMatches':'emptyTitle')}</h3><p>${FU(followupQuery||followupDepartment?'changeSearch':'emptyHint')}</p></div>`;
 return `<div class="followup-result-caption"><span>${I18N.tr(followupPrefix+'studentsCount',{count:I18N.number(rows.length)})}</span><small>${FU('amountsCurrent')}</small></div><div class="followup-list">${rows.slice((followupPage-1)*20,followupPage*20).map(followupCard).join('')}</div><div class="pager followup-pager"><button type="button" class="secondary" data-followup-page="-1" ${followupPage===1?'disabled':''}>${FU('previous')}</button><span>${I18N.number(followupPage)} / ${I18N.number(pages)}</span><button type="button" class="secondary" data-followup-page="1" ${followupPage===pages?'disabled':''}>${FU('next')}</button></div>`;
}
function followupRepaint(){
 const summary=$('#followup-summary'),results=$('#followup-results');
 if(summary)summary.innerHTML=followupSummary();if(results)results.innerHTML=followupResults();
}
function followupBody(){
 if(followupLoading)return `<section class="panel followup-loading" role="status">${FU('loading')}</section>`;
 if(followupError)return `<section class="panel"><p class="error" role="alert">${esc(followupError)}</p><button type="button" class="secondary" data-followup-refresh>${FU('retry')}</button></section>`;
 if(!followupData)return '';
 const names=new Map();followupItems().forEach(row=>names.set(String(row.department_id??'none'),row.department||FU('noDepartment')));
 if(followupDepartment&&!names.has(followupDepartment))followupDepartment='';
 return `<section class="panel followup-panel"><div class="followup-toolbar"><div class="followup-summary" id="followup-summary">${followupSummary()}</div><div class="followup-controls"><button type="button" class="secondary small" data-followup-refresh aria-label="${FU('refresh')}" title="${FU('refresh')}">↻</button></div></div><div class="followup-tools"><input type="search" id="followup-search" aria-label="${FU('search')}" maxlength="120" value="${esc(followupQuery)}" placeholder="${FU('searchHint')}" autocomplete="off"><select id="followup-department" aria-label="${FU('department')}"><option value="">${FU('allDepartments')}</option>${[...names].sort((a,b)=>a[1].localeCompare(b[1],I18N.lang)).map(([id,name])=>`<option value="${esc(id)}" ${followupDepartment===id?'selected':''}>${esc(name)}</option>`).join('')}</select></div><div id="followup-results" aria-live="polite">${followupResults()}</div></section>`;
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
const followupLogin=liveLoginScreen;
liveLoginScreen=function(){invalidateFollowup();followupQuery='';followupDepartment='';followupPage=1;followupOnScreen=false;$('#nav-followup')?.remove();followupLogin();};
document.addEventListener('input',event=>{if(event.target.id==='followup-search'){followupQuery=event.target.value;followupPage=1;followupRepaint();}});
document.addEventListener('change',event=>{if(event.target.id==='followup-department'){followupDepartment=event.target.value;followupPage=1;followupRepaint();}});
document.addEventListener('click',async event=>{
 const button=event.target.closest('button');if(!button||!button.matches('[data-followup-refresh],[data-followup-page],[data-followup-profile],[data-followup-pay],[data-followup-details]'))return;
 event.preventDefault();event.stopImmediatePropagation();if(!followupAllowed())return;
 if(button.hasAttribute('data-followup-refresh')){invalidateFollowup();loadFollowup();return;}
 if(button.dataset.followupDetails){followupDetails(button.dataset.followupDetails);return;}
 if(button.dataset.followupPage){followupPage+=Number(button.dataset.followupPage);followupRepaint();$('#followup-results')?.scrollIntoView({block:'start'});return;}
 const id=button.dataset.followupProfile||button.dataset.followupPay,row=followupItems().find(item=>String(item.id)===id);if(!row)return;
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
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&followupActive()&&followupAllowed()&&!followupLoading){invalidateFollowup();loadFollowup();}});
if(liveSession&&liveData)render();
