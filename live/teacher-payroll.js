/* The teacher file uses the school's existing cards, dialogs and cash services. */
'use strict';
const payPrefix='payroll.';
const payText=(key,args)=>I18N.tr(payPrefix+key,args);
const payMonth=value=>/^\d{4}-(0[1-9]|1[0-2])$/.test(value)&&value>='1990-01'&&value<='2099-12'?new Intl.DateTimeFormat(I18N.lang==='fr'?'fr-FR':'ar-MR-u-nu-latn',{month:'long',year:'numeric'}).format(new Date(value+'-02T12:00:00')):String(value||'—');
const payMoney=value=>money(value)+' '+payText('currency');
let payTab='months',payYear=null,payListPage=1,payQuoteRequest=0;
function payList(items,renderRows){const pages=Math.max(1,Math.ceil(items.length/20));payListPage=Math.min(payListPage,pages);return renderRows(items.slice((payListPage-1)*20,payListPage*20))+(pages>1?`<div class="pager"><button class="secondary small" data-pay-list-page="-1" ${payListPage===1?'disabled':''}>${I18N.tr('ui.a9e9d067101a')}</button><span>${payListPage} / ${pages}</span><button class="secondary small" data-pay-list-page="1" ${payListPage===pages?'disabled':''}>${I18N.tr('ui.5cf7af74fd3a')}</button></div>`:'');}
const payStatus=p=>`<span class="status pay-status ${p.status}">${payText('status.'+p.status)}</span>`;
const payNumber=(name,label,value,extra='')=>`<label>${label}<input name="${name}" type="number" min="0" max="99999999.99" step="0.01" value="${esc(value??0)}" required ${extra}></label>`;
Object.assign(recordNames,{teacher_salary_months:payText('history.teacher_salary_months'),teacher_advance_settlements:payText('history.teacher_advance_settlements')});
teacherProfile=function(t){
 const dep=personDepartments().find(d=>d.id===t.department_id)?.name||payText('noDepartment');
 return heading(payText('file'),payText('fileIntro'),`<button class="secondary" data-teacher-back>${payText('back')}</button>`)+
 `<section class="panel pay-identity"><div class="teacher-avatar large">${esc(t.name.slice(0,1))}</div><div class="pay-name"><h2>${esc(t.name)}</h2><div class="file-tags"><span class="status">${esc(dep)}</span><span class="status ${t.cancelled?'amber':''}">${payText(t.cancelled?'archived':'active')}</span></div></div>${!t.cancelled&&personCan('teachers.edit')?`<button class="secondary small" data-teacher-edit="${esc(t.id)}">${payText('editInfo')}</button>`:''}
 <div class="pay-contact">${fileFields([[payText('identity'),t.identity],[payText('phone'),t.phone],[payText('hireDate'),I18N.date(t.hire_date)],...(t.salary!==null?[[payText('monthlySalary'),payMoney(t.salary)]]:[])])}</div></section>`+
 (personCan('salaries.view')?`<section class="panel pay-account"><div class="person-section-head"><h2>${payText('account')}</h2><div class="actions">${!t.cancelled&&personCan('salaries.create')?`<button class="secondary" data-teacher-salary="salary">${payText('paySalary')}</button><button class="secondary" data-teacher-salary="advance">${payText('payAdvance')}</button>`:''}</div></div><div id="teacher-finance">${teacherFinanceHTML()}</div></section>`:'')+
 attendancePanel('teachers',t.id)+(!t.cancelled&&personCan('teachers.delete')?`<div class="pay-file-end"><button class="quiet" data-teacher-archive="${esc(t.id)}">${payText('archiveFile')}</button></div>`:'');
};
teacherFinanceHTML=function(){
 const a=teacherFinance;if(!a?.summary)return `<p class="tools-pending">${payText('loading')}</p>`;
 const s=a.summary,card=(title,n,hint='')=>`<div class="pay-metric"><span>${title}</span><strong>${n}</strong>${hint?'<small>'+hint+'</small>':''}</div>`;
 let html=`<div class="pay-metrics">${card(payText('paidMonths'),money(s.paid_months),s.partial_months?payText('partialCount',{count:money(s.partial_months)}):payText('completeOnly'))}${card(payText('advanceBalance'),payMoney(s.advance_balance),s.review_advances?payText('reviewAdvanceCount',{count:s.review_advances}):payText('knownAdvances'))}${card(payText('dueSalary'),payMoney(s.overdue),payText('dueAtMonthEnd'))}${card(payText('cashPaid'),payMoney(s.salary_cash),payText('cashOnly'))}</div>`;
 if(s.review_months||s.review_advances)html+=`<p class="pay-note">${payText('legacyNotice')}</p>`;
 html+=`<div class="pay-toolbar"><div class="pay-tabs" role="tablist">${['months','advances','movements'].map(k=>`<button type="button" role="tab" aria-selected="${payTab===k}" class="${payTab===k?'selected':''}" data-pay-tab="${k}">${payText(k)}</button>`).join('')}</div>${payTab==='months'?`<label class="pay-year">${payText('year')}<select id="pay-year">${a.years.map(y=>`<option ${a.year===y?'selected':''}>${y}</option>`).join('')}</select></label>`:''}</div>`;
 if(payTab==='months')html+=`<div class="pay-months">${a.periods.slice().reverse().map(p=>`<button type="button" class="pay-month" data-pay-month="${p.salary_month}"><div><strong>${esc(payMonth(p.salary_month))}</strong><small>${payText('settledOf',{paid:money(p.settled),total:money(p.entitlement)})}</small></div><div>${payStatus(p)}<small>${p.status==='review'?(Number(p.overpaid)?payText('overpaidAmount',{amount:payMoney(p.overpaid)}):payText('status.review')):p.remaining?payText('remainingAmount',{amount:payMoney(p.remaining)}):payText(p.status==='none'?'status.none':'complete')}</small></div><span aria-hidden="true">${I18N.lang==='fr'?'›':'‹'}</span></button>`).join('')||`<p class="empty">${payText('noMonths')}</p>`}</div>`;
 if(payTab==='advances')html+=payList(a.advances.slice().reverse(),rows=>rows.map(a=>`<button type="button" class="pay-month" data-pay-entry="advance" data-id="${a.id}"><div><strong>${payMoney(a.amount)}</strong><small>${I18N.date(a.advance_date)} · ${esc(payMonth(a.salary_month))}</small></div><div><span class="status ${a.review_required?'amber':''}">${payText(a.entry_cancelled_at?'cancelled':a.review_required?'reviewLoan':a.remaining?'loanOutstanding':'loanSettled')}</span><small>${payText('remainingAmount',{amount:payMoney(a.remaining)})}</small></div><span aria-hidden="true">${I18N.lang==='fr'?'›':'‹'}</span></button>`).join('')||`<p class="empty">${payText('noAdvances')}</p>`);
 if(payTab==='movements')html+=payList(a.salaries,payMovementRows);
 return html;
};
function payMovementRows(rows){return rows.map(r=>`<button type="button" class="pay-month" data-pay-entry="salary" data-id="${r.id}"><div><strong>${esc(payMonth(r.salary_month))}</strong><small>${payText('cashDate')} ${I18N.date(r.payment_date)}</small></div><div><strong>${payMoney(r.cash_amount)}</strong><small>${payText(r.entry_cancelled_at?'cancelled':r.record_state==='cancelled'?'voidCashRetained':'cashPayment')}${Number(r.advance)?' · '+payText('recoveryAmount',{amount:payMoney(r.advance)}):''}</small></div><span aria-hidden="true">${I18N.lang==='fr'?'›':'‹'}</span></button>`).join('')||`<p class="empty">${payText('noPayments')}</p>`;}
loadTeacherFinance=async function(){
 if(teacherFinanceLoading===teacherId||!teacherId||!personCan('salaries.view'))return;
 const id=teacherId,request=++teacherFinanceRequest;teacherFinanceLoading=id;
 try{const result=await liveCall('teachers.finance',{teacher:id,...(payYear?{year:payYear}:{})});if(id===teacherId&&request===teacherFinanceRequest){teacherFinance=result;const box=$('#teacher-finance');if(box)box.innerHTML=teacherFinanceHTML();}}
 catch(e){const box=$('#teacher-finance');if(box)box.innerHTML=`<p class="error">${esc(e.message)}</p><button class="secondary" data-pay-reload>${payText('retry')}</button>`;}
 finally{if(request===teacherFinanceRequest)teacherFinanceLoading=false;}
};
async function payOpenMonth(key){
 const p=teacherFinance.periods.find(p=>p.salary_month===key);if(!p)return;
 const t=liveData.teachers.find(t=>t.id===teacherId);
 openProtected(payMonth(key),`<div class="pay-month-detail"><div class="pay-detail-title">${payStatus(p)}<strong>${payMoney(p.entitlement)}</strong></div>${fileFields([[payText('base'),payMoney(p.base_salary)],[payText('bonus'),payMoney(p.bonus)],[payText('otherDeductions'),payMoney(p.deductions)],[payText('cashPaid'),payMoney(p.cash_paid)],[payText('advanceRecovery'),payMoney(p.recovered)],[payText('remaining'),payMoney(p.remaining)]])}${p.status==='review'?`<p class="pay-note">${payText('reviewMonthNotice')}</p>`:''}<div class="actions body-space">${p.remaining&&!p.review_required&&!p.overpaid&&!t.cancelled&&personCan('salaries.create')?`<button class="secondary" data-pay-month-salary="${key}">${payText('payRemaining')}</button>`:''}${personCan('salaries.edit')?`<button class="secondary" data-pay-edit-month="${key}">${payText('editEntitlement')}</button>`:''}</div><h3 class="body-space">${payText('monthPayments')}</h3>${payMovementRows(teacherFinance.salaries.filter(r=>r.salary_month===key))}</div>`);
}
async function payEditMonth(key,owner=teacherId){
 const q=await liveCall('payroll.quote',{teacher:owner,month:key}),p=q.period;
 openProtected(payText('editEntitlement')+' · '+payMonth(key),`<form id="pay-month-form" data-teacher="${esc(owner)}" data-month="${key}" data-revision="${q.revision}"><p class="muted">${payText('entitlementHint')}</p><div class="form-grid body-space">${payNumber('base',payText('base'),p.base_salary)}${payNumber('bonus',payText('bonus'),p.bonus)}${payNumber('deductions',payText('otherDeductions'),p.deductions)}</div><p class="notice-box" id="pay-month-net">${payMoney(p.entitlement)}</p>${confirmation()}</form>`);
 const f=$('#pay-month-form');f.oninput=()=>{$('#pay-month-net').textContent=payText('monthNet',{amount:payMoney(Number(f.elements.base.value)+Number(f.elements.bonus.value)-Number(f.elements.deductions.value))});};
}
const originalSalaryWindow=salaryWindow;
salaryWindow=function(kind,options={}){
 const row=options.row,chosen=options.teacher||teacherId||'',key=row?.salary_month||options.month||today.slice(0,7);
 const archivedOwner=row?teacherOptions.find(t=>t.id===chosen&&t.archived):null;
 const archivedOption=archivedOwner?`<option value="${esc(chosen)}">${esc(archivedOwner.name)} · ${payText('archived')}</option>`:'';
 openProtected(payText(row?'editPayment':kind==='salary'?'paySalary':'payAdvance'),`<form id="payroll-form" data-kind="${kind}" ${row?'data-edit="'+row.id+'"':''}><label>${payText('teacher')}<select name="teacher" required ${row?'disabled':''}>${teacherChoices()}${archivedOption}</select></label><div class="form-grid body-space">${fieldInput({key:'month',label:payText(kind==='salary'?'salaryMonth':'recoveryMonth'),type:'month',required:true},key)}${fieldInput({key:'date',label:payText('cashDate'),type:'date',required:true},row?(row.payment_date||row.advance_date||''):today)}</div><div id="pay-quote" class="body-space"><p class="muted">${payText('chooseTeacher')}</p></div><label class="body-space">${payText('notes')}<input name="notes" value="${esc(row?.notes||'')}"></label>${confirmation()}</form>`);
 const f=$('#payroll-form');f.elements.teacher.value=chosen;
 let q=null;
 const refresh=async()=>{
  const request=++payQuoteRequest,id=f.elements.teacher.value,m=f.elements.month.value;
  const sameOwner=f.dataset.teacher===id;
  const manualCash=sameOwner&&f.dataset.cashAuto==='false'&&f.elements.payment_cash?f.elements.payment_cash.value:null;
  const manualRecoveries=sameOwner&&f.dataset.recoveriesTouched==='true'?Object.fromEntries([...f.querySelectorAll('[data-pay-recovery]')].map(e=>[e.dataset.payRecovery,e.value])):null;
  if(!sameOwner)delete f.dataset.recoveriesTouched;
  if(f.dataset.ready)f.elements.confirmed.checked=false;
  f.querySelector('button.primary').disabled=true;
  if(!id||!m)return;
  try{
   const result=await liveCall('payroll.quote',{teacher:id,month:m,...(row&&kind==='salary'?{payment:row.id}:{})});
   if(request!==payQuoteRequest||!f.isConnected)return;q=result;f._payQuote=q;f._payRow=row;f.dataset.teacher=id;f.dataset.quoteMonth=m;
   if(q.archived&&!row)throw Error(payText('archivedNoPay'));
   const p=q.period;
   if(kind==='advance')$('#pay-quote').innerHTML=payNumber('amount',payText('advanceAmount'),row?.amount||0)+`<p class="muted body-space">${payText('advanceHint')}</p><p class="pay-note" id="pay-advance-impact" hidden></p>`;
   else{
    let room=Number(p.remaining);const day=f.elements.date.value;
    const loans=q.advances.filter(a=>!a.entry_cancelled_at&&!a.review_required&&Number(a.remaining)>0&&a.salary_month<=m&&a.advance_date<=day);
    const recoveries=loans.map(a=>{const before=row?.settlements?.find(x=>x.id===a.advance_id)?.amount;const amount=manualRecoveries?(manualRecoveries[a.advance_id]??0):row?Number(before||0):Math.min(Math.max(0,room),Number(a.remaining));room=Math.round((room-Number(amount||0))*100)/100;return {...a,chosen:amount};});
    $('#pay-quote').innerHTML=`<div class="pay-quote-summary"><span>${payText('remainingSalary')}</span><strong id="salary-net">${payMoney(p.remaining)}</strong></div><div class="form-grid body-space">${payNumber('base',payText('base'),p.base_salary,p.month_id?'readonly':'')}${payNumber('bonus',payText('bonus'),p.bonus,p.month_id?'readonly':'')}${payNumber('deductions',payText('otherDeductions'),p.deductions,p.month_id?'readonly':'')}</div>${recoveries.length?`<details class="pay-loans body-space" open><summary>${payText('advanceRecovery')}</summary>${recoveries.map(a=>`<label class="pay-recovery"><span>${I18N.date(a.advance_date)}<small>${payText('loanBalance',{amount:payMoney(a.remaining)})}</small></span><input type="number" data-pay-recovery="${a.advance_id}" min="0" max="${a.remaining}" step="0.01" value="${a.chosen}" aria-label="${payText('recoveryFor',{date:I18N.date(a.advance_date)})}"></label>`).join('')}</details>`:''}${payNumber('payment_cash',payText('cashToPay'),row?.cash_amount??Math.max(0,room))}<p class="notice-box" id="pay-check"></p>${q.advances.some(a=>a.review_required&&a.remaining)?`<p class="pay-note">${payText('oldLoanNotAuto')}</p>`:''}${p.review_required||p.overpaid?`<p class="error">${payText('reviewMonthNotice')}</p>`:''}`;
    if(manualCash!==null)f.elements.payment_cash.value=manualCash;
    f.dataset.cashAuto=row||manualCash!==null?'false':'true';
   }
   f.querySelector('button.primary').disabled=kind==='salary'&&((p.review_required&&!row)||p.overpaid||Number(p.remaining)<=0);
   payUpdateQuote(f);
   if(!f.dataset.ready){f.dataset.ready='true';if(f.elements.teacher.value===chosen&&f.elements.month.value===key)protectEditWindow($('#record-dialog'),['workspace-close']);}
  }catch(e){if(request===payQuoteRequest&&f.isConnected)$('#pay-quote').innerHTML=`<p class="error">${esc(e.message)}</p>`;}
 };
 f.elements.teacher.onchange=refresh;f.elements.month.onchange=refresh;
 f.elements.date.onchange=()=>{if(q&&kind==='salary')payUpdateQuote(f);};
 f.oninput=e=>{if(e.target.name==='payment_cash')f.dataset.cashAuto='false';if(e.target.dataset.payRecovery)f.dataset.recoveriesTouched='true';payUpdateQuote(f);};refresh();
};
function payUpdateQuote(f){
 const q=f._payQuote,box=$('#pay-check');if(!q)return;
 if(f.dataset.kind==='advance'){const impact=$('#pay-advance-impact'),released=Math.max(0,Number(f._payRow?.repaid||0)-Number(f.elements.amount.value||0));if(impact){impact.hidden=!released;impact.textContent=payText('reopenAmount',{amount:payMoney(released)});}return;}
 if(!box)return;
 const recovered=[...f.querySelectorAll('[data-pay-recovery]')].reduce((n,e)=>n+Number(e.value||0),0);
 const p=q.period,target=Number(f.elements.base.value)+Number(f.elements.bonus.value)-Number(f.elements.deductions.value);
 const remaining=target-Number(p.settled);
 if(f.dataset.cashAuto==='true')f.elements.payment_cash.value=String(Math.max(0,Math.round((remaining-recovered)*100)/100));
 const paid=Number(f.elements.payment_cash.value||0);$('#salary-net').textContent=payMoney(remaining);
 f.querySelector('button.primary').disabled=!!((p.review_required&&!f._payRow)||p.overpaid||remaining<=0||!f.elements.month.value||!f.elements.teacher.value);
 box.textContent=payText('paymentPreview',{cash:payMoney(paid),recovery:payMoney(recovered),remaining:payMoney(Math.max(0,remaining-paid-recovered))});
 box.classList.toggle('pay-invalid',paid+recovered>remaining+.001||paid<0||recovered<0);
}
async function payEntry(kind,id){
 const rows=kind==='salary'?teacherFinance.salaries:teacherFinance.advances,r=rows.find(r=>r.id===id);if(!r)return;
 const loan=kind==='advance';
 let body=`<div class="pay-detail-title"><span>${esc(payMonth(r.salary_month))}</span><strong>${payMoney(r.cash_amount)}</strong></div>${fileFields([[payText('cashDate'),I18N.date(r.payment_date||r.advance_date)],...(loan?[[payText('loanRepaid'),payMoney(r.repaid)],[payText('remaining'),payMoney(r.remaining)]]:[[payText('base'),payMoney(r.base_salary)],[payText('bonus'),payMoney(r.bonus)],[payText('otherDeductions'),payMoney(r.deductions)],[payText('advanceRecovery'),payMoney(r.advance)]])])}`;
 if(r.notes)body+=`<p class="body-space">${esc(r.notes)}</p>`;
 if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(r.salary_month))body+=`<p class="pay-note">${payText('invalidMonthHint')}</p>`;
 const unlinked=!loan&&!r.managed_month?Math.max(0,Number(r.advance)-(r.settlements||[]).reduce((s,a)=>s+Number(a.amount),0)):0;
 if(unlinked&&personCan('salaries.edit'))body+=`<p class="pay-note">${payText('unlinkedHint',{amount:payMoney(unlinked)})}</p><button class="secondary" data-pay-clear-unlinked="${r.id}">${payText('correctUnlinked')}</button>`;
 if(loan&&r.recoveries?.length)body+=`<h3 class="body-space">${payText('recoveredThrough')}</h3><div>${r.recoveries.map(x=>`<button class="pay-month" data-pay-entry="salary" data-id="${x.payment_id}"><strong>${esc(payMonth(x.salary_month))}</strong><span>${payMoney(x.amount)}</span><span aria-hidden="true">${I18N.lang==='fr'?'›':'‹'}</span></button>`).join('')}</div>`;
 if(r.entry_cancelled_at)body+=`<p class="pay-note">${payText('cancelled')}</p>`;
 else if(r.record_state==='cancelled')body+=`<p class="pay-note">${payText('voidHint')}</p>`;
 if(!r.entry_cancelled_at){body+=`<div class="actions body-space">${personCan('salaries.edit')?`<button class="secondary" data-pay-edit="${kind}" data-id="${r.id}">${payText('editPayment')}</button>`:''}${personCan('salaries.delete')?`<button class="secondary danger" data-pay-cancel="${kind}" data-id="${r.id}">${payText('cancelEntry')}</button>`:''}${personCan('salaries.delete')&&r.record_state==='active'?`<button class="secondary" data-pay-void="${kind}" data-id="${r.id}">${payText('voidDocument')}</button>`:''}${!loan?`<button class="secondary" data-pay-pdf="${r.id}">${payText('downloadSlip')}</button>`:''}</div>`;}
 if(r.entry_cancelled_at&&!loan)body+=`<button class="secondary body-space" data-pay-pdf="${r.id}">${payText('downloadSlip')}</button>`;
 const canLink=loan&&!r.invalid_month&&(r.review_required||Number(r.legacy_repaid)||(Number(r.remaining)>0&&teacherFinance.salaries.some(p=>!p.entry_cancelled_at&&p.payment_date>=r.advance_date&&p.salary_month>=r.salary_month&&Number(p.deductions)>0)));
 if(canLink&&!r.entry_cancelled_at&&personCan('salaries.edit'))body+=`<div class="pay-legacy-actions"><p>${payText(r.review_required?'reviewLoanHint':'linkOldHint')}</p><button class="secondary" data-pay-reconcile="${r.id}">${payText('linkOldDeduction')}</button>${r.review_required?`<button class="secondary" data-pay-confirm-loan="${r.id}">${payText('confirmUnpaid')}</button>`:''}${Number(r.legacy_repaid)?`<button class="secondary" data-pay-legacy-status="${r.id}">${payText('editLegacyStatus')}</button>`:''}</div>`;
 openProtected(payText(loan?'advanceDetails':'salaryDetails'),body);
}
function payCancel(kind,id,voidOnly=false){
 const r=(kind==='salary'?teacherFinance.salaries:teacherFinance.advances).find(r=>r.id===id);
 openProtected(payText(voidOnly?'voidDocument':'cancelEntry'),`<form id="pay-cancel-form" data-kind="${kind}" data-id="${id}" data-void="${voidOnly}" data-revision="${r.revision}" data-account="${teacherFinance.revision}"><p class="pay-note">${payText(voidOnly?'voidHint':kind==='salary'?'cancelSalaryHint':'cancelAdvanceHint')}</p>${kind==='advance'&&!voidOnly&&Number(r.repaid)?`<p>${payText('reopenAmount',{amount:payMoney(r.repaid)})}</p>`:''}<strong>${payMoney(r.cash_amount)}</strong>${confirmation()}</form>`);
}
function payReconcile(id,confirmOnly=false){
 const r=teacherFinance.advances.find(r=>r.id===id);
 const available=teacherFinance.salaries.filter(p=>!p.entry_cancelled_at&&(Number(p.deductions)>0||(!p.managed_month&&Number(p.advance)>(p.settlements||[]).reduce((s,a)=>s+Number(a.amount),0)))&&p.payment_date>=r.advance_date&&p.salary_month>=r.salary_month);
 openProtected(payText(confirmOnly?'confirmUnpaid':'linkOldDeduction'),`<form id="pay-reconcile-form" data-id="${id}" data-confirm-only="${confirmOnly}" data-revision="${teacherFinance.revision}"><p class="pay-note">${payText(confirmOnly?'confirmUnpaidHint':'linkOldHint')}</p>${!confirmOnly?`<label>${payText('existingPayment')}<select name="payment" required><option value="">${payText('choosePayment')}</option>${available.map(p=>`<option value="${p.id}">${esc(payMonth(p.salary_month))} · ${I18N.date(p.payment_date)}</option>`).join('')}</select></label>${payNumber('amount',payText('reconcileAmount'),r.legacy_repaid||r.remaining)}`:''}${confirmation()}</form>`);
}
function payLegacyStatus(id){const r=teacherFinance.advances.find(r=>r.id===id);openProtected(payText('editLegacyStatus'),`<form id="pay-legacy-status-form" data-id="${id}" data-revision="${teacherFinance.revision}"><p class="pay-note">${payText('legacyStatusHint')}</p>${payNumber('amount',payText('previouslyRepaid'),r.legacy_repaid)}${confirmation()}</form>`);}
function payClearUnlinked(id){const r=teacherFinance.salaries.find(r=>r.id===id),amount=Number(r.advance)-(r.settlements||[]).reduce((s,a)=>s+Number(a.amount),0);openProtected(payText('correctUnlinked'),`<form id="pay-clear-unlinked-form" data-id="${id}" data-revision="${teacherFinance.revision}"><p class="pay-note">${payText('clearUnlinkedHint')}</p>${payNumber('amount',payText('wrongRecovery'),amount)}${confirmation()}</form>`);}
const payPreviousSubmit=liveSubmit;
liveSubmit=async function(form){
 const d=new FormData(form),get=k=>String(d.get(k)||'');let op,data;
 if(form.id==='pay-month-picker'){await payEditMonth(get('month'),get('teacher'));return;}
 if(form.id==='payroll-form'){
  const q=form._payQuote;if(!q)throw Error(payText('chooseTeacher'));
  const kind=form.dataset.kind,row=form._payRow;
  data={kind,teacher:form.dataset.teacher,month:get('month'),date:get('date'),base:get('base'),bonus:get('bonus')||'0',deductions:get('deductions')||'0',amount:get('amount'),payment_cash:get('payment_cash'),notes:get('notes'),reason:get('reason'),confirmed:d.has('confirmed'),managed:kind==='salary',account_revision:q.revision,
   settlements:[...form.querySelectorAll('[data-pay-recovery]')].filter(e=>Number(e.value)>0).map(e=>({id:Number(e.dataset.payRecovery),amount:e.value}))};
  op=row?'payroll.correct':'payroll.save';if(row)Object.assign(data,{id:row.id,revision:row.revision});
 }else if(form.id==='pay-month-form'){op='payroll.month';data={teacher:form.dataset.teacher,month:form.dataset.month,revision:form.dataset.revision,base:get('base'),bonus:get('bonus'),deductions:get('deductions'),reason:get('reason'),confirmed:d.has('confirmed')};}
 else if(form.id==='pay-cancel-form'){const kind=form.dataset.kind;op=form.dataset.void==='true'?'tools.change':'payroll.correct';data=op==='tools.change'?{table:kind==='salary'?'teacher_payments':'teacher_advances',mode:'void_document',id:Number(form.dataset.id),revision:form.dataset.revision}:{kind,id:Number(form.dataset.id),revision:form.dataset.revision,account_revision:form.dataset.account,cancel:true};Object.assign(data,{reason:get('reason'),confirmed:d.has('confirmed')});}
 else if(form.id==='pay-reconcile-form'){op=form.dataset.confirmOnly==='true'?'payroll.confirm-advance':'payroll.reconcile';data={teacher:teacherId,advance:Number(form.dataset.id),payment:Number(get('payment')),amount:get('amount'),revision:form.dataset.revision,reason:get('reason'),confirmed:d.has('confirmed')};}
 else if(form.id==='pay-legacy-status-form'){op='payroll.legacy-status';data={teacher:teacherId,advance:Number(form.dataset.id),amount:get('amount'),revision:form.dataset.revision,reason:get('reason'),confirmed:d.has('confirmed')};}
 else if(form.id==='pay-clear-unlinked-form'){op='payroll.clear-unlinked';data={teacher:teacherId,payment:Number(form.dataset.id),amount:get('amount'),revision:form.dataset.revision,reason:get('reason'),confirmed:d.has('confirmed')};}
 else return payPreviousSubmit(form);
 invalidateTeacherFinance();await liveSaved(op,data,form);if(page==='tools'&&toolTab==='records'){toolRows=null;loadToolRows();}pageTop();
};
document.addEventListener('change',e=>{if(e.target.id==='pay-year'){payYear=Number(e.target.value);invalidateTeacherFinance();render();}},true);
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 const attr=[...b.attributes].find(a=>a.name.startsWith('data-pay-'));if(!attr)return;
 e.preventDefault();e.stopImmediatePropagation();
 try{
  if(b.dataset.payTab){payTab=b.dataset.payTab;payListPage=1;$('#teacher-finance').innerHTML=teacherFinanceHTML();}
  else if(b.dataset.payListPage){payListPage+=Number(b.dataset.payListPage);$('#teacher-finance').innerHTML=teacherFinanceHTML();}
  else if(b.hasAttribute('data-pay-reload')){invalidateTeacherFinance();loadTeacherFinance();}
  else if(b.dataset.payMonth)await payOpenMonth(b.dataset.payMonth);
  else if(b.dataset.payEditMonth)await payEditMonth(b.dataset.payEditMonth);
  else if(b.dataset.payMonthSalary)salaryWindow('salary',{month:b.dataset.payMonthSalary});
  else if(b.dataset.payEntry)await payEntry(b.dataset.payEntry,Number(b.dataset.id));
  else if(b.dataset.payEdit){const kind=b.dataset.payEdit,row=(kind==='salary'?teacherFinance.salaries:teacherFinance.advances).find(r=>r.id===Number(b.dataset.id));teacherOptions=await liveCall('teachers.options');salaryWindow(kind,{row,teacher:teacherId});}
  else if(b.dataset.payCancel)payCancel(b.dataset.payCancel,Number(b.dataset.id));
  else if(b.dataset.payVoid)payCancel(b.dataset.payVoid,Number(b.dataset.id),true);
  else if(b.dataset.payReconcile)payReconcile(Number(b.dataset.payReconcile));
  else if(b.dataset.payConfirmLoan)payReconcile(Number(b.dataset.payConfirmLoan),true);
  else if(b.dataset.payLegacyStatus)payLegacyStatus(Number(b.dataset.payLegacyStatus));
  else if(b.dataset.payClearUnlinked)payClearUnlinked(Number(b.dataset.payClearUnlinked));
  else if(b.hasAttribute('data-pay-pick-month')){teacherOptions=await liveCall('teachers.options');openProtected(payText('chooseEntitlement'),`<form id="pay-month-picker"><label>${payText('teacher')}<select name="teacher" required><option value="">${payText('chooseTeacher')}</option>${teacherOptions.map(t=>`<option value="${esc(t.id)}">${esc(t.name+' · '+t.identity)}${t.archived?' · '+payText('archived'):''}</option>`).join('')}</select></label><div class="body-space">${fieldInput({key:'month',label:payText('salaryMonth'),type:'month',required:true},today.slice(0,7))}</div><p class="error" role="alert"></p><button class="secondary body-space">${payText('openEntitlement')}</button></form>`);}
  else if(b.dataset.payPdf){
   const r=await fetch('/api/payroll.pdf',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','Origin':location.origin,'X-CSRF-Token':liveSession.csrf,'X-App-Language':I18N.lang},body:JSON.stringify({id:Number(b.dataset.payPdf)})});
   if(!r.ok)throw liveResponseError(r,await r.json());const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download='salary-slip.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
 }catch(error){toast(error.message,'error');}
},true);

const payOriginalTeacherEditor=teacherEditor;
teacherEditor=function(id=null){payOriginalTeacherEditor(id);if(id)document.querySelector('#teacher-form .form-grid')?.insertAdjacentHTML('afterend','<p class="muted body-space">'+payText('salaryRateHint')+'</p>');};
const payOriginalToolEditor=toolEditor;
toolEditor=async function(id,mode){
 if(!['teacher_payments','teacher_advances'].includes(toolTable))return payOriginalToolEditor(id,mode);
 try{
  const entry=toolRows?.items.find(r=>String(r.id)===String(id));if(!entry?.teacher)return payOriginalToolEditor(id,mode);
  const kind=toolTable==='teacher_payments'?'salary':'advance';
  teacherId=entry.teacher;teacherFinance=await liveCall('teachers.finance',{teacher:teacherId});teacherOptions=await liveCall('teachers.options');
  const row=(kind==='salary'?teacherFinance.salaries:teacherFinance.advances).find(r=>r.id===Number(id));
  if(mode==='edit')salaryWindow(kind,{row,teacher:teacherId});else payCancel(kind,Number(id),mode==='void_document');
 }catch(error){toast(error.message,'error');}
};
const payOriginalLoginScreen=liveLoginScreen;
liveLoginScreen=function(){payQuoteRequest++;payYear=null;payTab='months';payListPage=1;$('#record-content')?.replaceChildren();$('#receipt-content')?.replaceChildren();payOriginalLoginScreen();};
const payOriginalPayrollScreen=payrollScreen;
payrollScreen=function(can){return payOriginalPayrollScreen(can)+(personCan('salaries.edit')&&!personCan('teachers.view')?`<div class="actions body-space"><button class="secondary" data-pay-pick-month>${payText('editEntitlement')}</button></div>`:'');};
