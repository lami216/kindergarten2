/* One reports page; dates and export always refer to the displayed snapshot. */
'use strict';
const RP=k=>I18N.tr(`reports.${k}`);
let financeMode='finance',financeData=null,financeLoading=false,financeSequence=0,financeCategory='all',financeQuery='',financePage=1;
let financeDates=null;
function financeAllowed(){return !!liveSession&&(demoActor.admin||liveSession.user.permissions.includes('reports.view'));}
const reportsMayPage=demoMayPage;
demoMayPage=function(target){return target==='reports'?financeAllowed():reportsMayPage(target);};
function financeHasOther(){return ['students','receipts','expenses','salaries'].some(area=>demoCan(area));}
function financeDefaults(){return financeDates||(financeDates={start:today.slice(0,8)+'01',end:today});}
function financeRange(){return {start:$('#fin-start')?.value||'',end:$('#fin-end')?.value||''};}
function financeMatches(){const v=financeRange();return !!financeData&&v.start===financeData.start&&v.end===financeData.end;}
function financePageHTML(){
 const dates=financeDefaults();if(!financeHasOther())financeMode='finance';
 return `<div id="finance-page">${heading(RP('title'),RP('subtitle'))}<div class="choices fin-controls"><button class="choice ${financeMode==='finance'?'active':''}" data-report-mode="finance">${RP('finance')}</button>${financeHasOther()?`<button class="choice ${financeMode==='other'?'active':''}" data-report-mode="other">${RP('other')}</button>`:''}</div>${financeMode==='other'?reportScreen():`<form id="finance-report-form" class="panel fin-controls"><div class="fin-presets">${['today','last7','thisMonth','lastMonth','custom'].map(k=>`<button type="button" class="secondary small" data-fin-period="${k}">${RP(k)}</button>`).join('')}</div><div class="fin-dates"><label>${RP('from')}<input type="date" id="fin-start" name="start" required max="${today}" value="${esc(dates.start)}"></label><label>${RP('to')}<input type="date" id="fin-end" name="end" required max="${today}" value="${esc(dates.end)}"></label><button class="primary" ${financeLoading?'disabled':''}>${financeLoading?RP('pending'):RP('show')}</button></div><p class="error" role="alert"></p></form><section id="finance-output">${financeOutput()}</section>`}</div>`;
}
function financeCard(key,value,filter,icon){return `<button type="button" class="fin-card" data-fin-filter="${filter}" aria-pressed="${financeCategory===filter}"><span>${icon} ${RP(key)}</span><strong>${money(value)}</strong><small>${RP('currency')}</small></button>`;}
function financeOutput(){
 if(financeLoading)return `<div class="panel" role="status">${RP('pending')}</div>`;
 if(!financeData)return `<div class="panel empty" role="status">${RP('empty')}</div>`;
 const r=financeData,s=r.summary;
 return `<div class="fin-report-meta"><strong>${RP('period')}: ${esc(I18N.date(r.start))} — ${esc(I18N.date(r.end))}</strong><small>${RP('generated')} ${esc(new Date(r.generated_at).toLocaleString(I18N.lang==='fr'?'fr-FR':'ar-MR'))}</small></div><div class="fin-cards">${financeCard('income',s.income,'income','↙')}${financeCard('outgoing',s.outgoing,'outgoing','↗')}${financeCard('net',s.net,'all','＝')}</div><div class="fin-balances"><span>${RP('opening')} <strong>${money(s.opening)}</strong></span><span>${RP('closing')} <strong>${money(s.closing)}</strong></span></div><p class="muted fin-notes">${RP('cashNote')}</p><div class="fin-breakdowns"><section class="panel"><h2>${RP('income')}</h2>${['registration','gilet','monthly',...(Number(s.other_income)?['other_income']:[])].map(k=>detailLine(RP(k),money(s[k]))).join('')}<small>${RP('prepaid')}: ${money(s.prepaid)}. ${RP('partNote')}</small></section><section class="panel"><h2>${RP('outgoing')}</h2>${['operational','salary','advance'].map(k=>detailLine(RP(k),money(s[k]))).join('')}</section></div><section class="panel"><div class="person-section-head"><h2>${RP('details')}</h2><div class="actions fin-export-actions"><button class="secondary" id="fin-xlsx">${RP('xlsx')}</button><button class="secondary" id="fin-print">${RP('print')}</button></div></div><p class="muted">${RP('filterNote')}</p><div class="fin-detail-controls fin-controls"><label>${RP('query')}<input id="fin-query" maxlength="120" value="${esc(financeQuery)}" placeholder="${RP('queryHint')}"></label><label>${RP('type')}<select id="fin-category">${['all','income','outgoing','operational','salary','advance'].map(k=>`<option value="${k}" ${k===financeCategory?'selected':''}>${RP(k)}</option>`).join('')}</select></label></div><div id="fin-ledger">${financeLedger()}</div></section><section class="panel fin-debts"><h2>${RP('debts')} · ${esc(I18N.date(r.end))}</h2><p class="muted">${RP('debtNote')}</p>${financeDebt('students','studentsDebt','payments')}${financeDebt('suppliers','suppliersDebt','expenses')}</section><p class="muted">${RP('correctionNote')}</p>`;
}
function financeRows(){
 const query=financeQuery.trim().normalize('NFKC').toLowerCase();
 return (financeData?.items||[]).filter(r=>(financeCategory==='all'||r.category===financeCategory||financeCategory==='outgoing'&&r.category!=='income')&&[r.label,r.party,r.source_id,r.date].map(v=>String(v??'')).join(' ').normalize('NFKC').toLowerCase().includes(query));
}
function financeRow(r){
 const student=r.student_id&&students.find(s=>s.id===r.student_id);
 const title=r.label||RP(r.category);
 const allocation=r.category==='income'?['registration','gilet','monthly'].filter(k=>Number(r[k])).map(k=>RP(k)+': '+money(r[k])).join(' · '):'';
 return `<tr><td>${esc(I18N.date(r.date))}</td><td>${RP(r.category+'Entry')}${r.void_document?`<small class="fin-row-note">${RP('voidDocument')}</small>`:''}</td><td><div class="row-person">${student?studentAvatar(student):''}<div><strong>${esc(title)}</strong><small class="fin-row-note">${esc(r.party||'')}${r.source_id?' · #'+esc(r.source_id):''}</small>${allocation?`<small class="fin-row-note">${esc(allocation)}</small>`:''}</div></div></td><td class="fin-amount ${r.category==='income'?'incoming':'outgoing'}">${r.category==='income'?'+':'−'}${money(r.amount)}</td><td class="fin-table-actions">${r.category==='income'&&financeData.permissions.payments&&r.source_id?`<button class="link-button" data-fin-receipt="${r.source_id}">${RP('open')}</button>`:''}</td></tr>`;
}
function financeTable(rows,extra=''){return `<div class="table-wrap ${extra}"><table><thead><tr>${['date','type','description','amount'].map(k=>'<th>'+RP(k)+'</th>').join('')}<th class="fin-table-actions"></th></tr></thead><tbody>${rows.map(financeRow).join('')}</tbody></table></div>`;}
function financeLedger(){
 const rows=financeRows(),pages=Math.max(1,Math.ceil(rows.length/25));financePage=Math.min(financePage,pages);
 const total=rows.reduce((n,r)=>n+(r.category==='income'?Number(r.amount):-Number(r.amount)),0);
 return `<div class="fin-filter-summary"><strong>${I18N.tr('reports.count',{count:rows.length})}</strong><span>${RP('filteredTotal')}: <b>${money(Math.round(total*100)/100)}</b> ${RP('currency')}</span><small>${RP(financeCategory)}${financeQuery?' · '+esc(financeQuery):''}</small></div>${rows.length?financeTable(rows.slice((financePage-1)*25,financePage*25),'fin-screen-table'):`<p class="empty">${RP('noRows')}</p>`}${financeTable(rows,'fin-print-table')}<div class="pager fin-controls"><button class="secondary" data-fin-page="-1" ${financePage===1?'disabled':''}>${RP('previous')}</button><span>${financePage} / ${pages}</span><button class="secondary" data-fin-page="1" ${financePage===pages?'disabled':''}>${RP('next')}</button></div>`;
}
function financeDebt(key,title,permission){const d=financeData.debt;return `<details><summary>${RP(title)} <strong>${money(d[key+'_total'])} ${RP('currency')}</strong></summary>${financeData.permissions[permission]?d[key].map(r=>`<div class="list-card"><span>${esc(r.name)}${r.archived?' · '+RP('archived'):''}${r.payee?' · '+esc(r.payee):''}</span><strong>${money(r.amount)}</strong></div>`).join('')||`<p class="muted">${RP('noRows')}</p>`:`<p class="muted">${RP('restricted')}</p>`}</details>`;}
function financeUpdateLedger(){const block=$('#fin-ledger');if(block)block.innerHTML=financeLedger();$('#fin-category').value=financeCategory;document.querySelectorAll('[data-fin-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.finFilter===financeCategory)));}
async function loadFinance(form){
 if(!financeAllowed()||!form.reportValidity())return;
 const dates=financeRange();if(dates.start>dates.end){form.querySelector('.error').textContent=I18N.sourceLabel('راجع تاريخ البداية والنهاية.');return;}
 const version=++financeSequence,identity=liveSession;financeDates=dates;financeData=null;financeLoading=true;$('#finance-output').innerHTML=financeOutput();form.querySelector('button.primary').disabled=true;
 try{const result=await liveCall('reports.finance',dates);if(version!==financeSequence||liveSession!==identity||page!=='reports'||financeMode!=='finance')return;financeData=result;financePage=1;financeLoading=false;$('#finance-output').innerHTML=financeOutput();toast(RP('saved'));}
 catch(e){if(version===financeSequence&&page==='reports'){form.querySelector('.error').textContent=e.message;$('#finance-output').innerHTML='';}}
 finally{if(version===financeSequence){financeLoading=false;if(form.isConnected)form.querySelector('button.primary').disabled=false;}}
}
function financePreset(name){
 if(name==='custom'){$('#fin-start').previousElementSibling?.querySelector('input')?.focus();return;}
 const now=new Date(today+'T12:00:00'),format=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
 let start=today,end=today;
 if(name==='last7'){now.setDate(now.getDate()-6);start=format(now);}
 if(name==='thisMonth')start=today.slice(0,8)+'01';
 if(name==='lastMonth'){now.setDate(0);end=format(now);now.setDate(1);start=format(now);}
 $('#fin-start').value=start;$('#fin-end').value=end;loadFinance($('#finance-report-form'));
}
function otherReportFields(){const f=$('#report-form');if(!f)return;const kind=f.elements.kind.value;for(const name of ['start','end','teacher']){const el=f.elements[name],visible=name==='teacher'?kind==='salaries':name==='start'?!['students','debt'].includes(kind):kind!=='students';el.closest('label').hidden=!visible;el.disabled=!visible;if(name!=='teacher')el.required=visible;}const opt=f.querySelector('[name="kind"] option[value="expenses"]');if(opt)opt.textContent=RP('invoiceReport');let note=$('#fin-invoice-note');if(!note){note=document.createElement('p');note.id='fin-invoice-note';note.className='muted';f.append(note);}note.textContent=kind==='expenses'?RP('invoiceNote'):'';}
const reportsRender=render;
render=function(){
 if(page==='tools'&&toolTab==='reports'&&financeAllowed()){page='reports';financeMode='other';}
 if(page==='reports'&&financeAllowed()){
  $('#crumb').textContent=RP('title');$('#content').innerHTML=financePageHTML();document.querySelectorAll('nav [data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page==='reports');b.setAttribute('aria-current',b.dataset.page==='reports'?'page':'false');});
  if(financeMode==='other'){const option=$('#report-form option[value="finance"]');option?.remove();otherReportFields();if(!teacherOptions.length&&demoCan('salaries'))liveCall('teachers.options').then(options=>{teacherOptions=options;const f=$('#report-form');if(f)f.elements.teacher.innerHTML=reportTeacherChoices(f.elements.teacher.value);}).catch(e=>toast(e.message,'error'));}
 }else reportsRender();
 if(financeAllowed()&&!$('#nav-reports')){const b=document.createElement('button');b.id='nav-reports';b.dataset.page='reports';b.innerHTML='📋 <span>'+RP('title')+'</span>';b.onclick=()=>{financeMode='finance';navigate('reports');};document.querySelector('nav').insertBefore(b,$('#nav-workspace')||$('#demo-logout'));}
 if(!financeAllowed())$('#nav-reports')?.remove();
};
const reportsLogin=liveLoginScreen;
liveLoginScreen=function(){financeSequence++;financeData=null;financeDates=null;financeQuery='';financeCategory='all';financeLoading=false;$('#nav-reports')?.remove();reportsLogin();};
const reportsSubmit=liveSubmit;
liveSubmit=async function(form){if(form.id==='finance-report-form')return loadFinance(form);return reportsSubmit(form);};
const reportsSaved=liveSaved;
liveSaved=async function(...args){const result=await reportsSaved(...args);financeSequence++;financeData=null;return result;};
document.addEventListener('input',e=>{if(e.target.id==='fin-start'||e.target.id==='fin-end'){financeSequence++;financeData=null;financeLoading=false;financeDates=financeRange();$('#finance-output').innerHTML=`<div class="panel" role="status">${RP('stale')}</div>`;$('#finance-report-form button.primary').disabled=false;}if(e.target.id==='fin-query'){financeQuery=e.target.value;financePage=1;financeUpdateLedger();}});
document.addEventListener('change',e=>{if(e.target.id==='fin-category'){financeCategory=e.target.value;financePage=1;financeUpdateLedger();}if(e.target.matches('#report-form [name="kind"]'))otherReportFields();});
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;const data=b.dataset;
 if(!b.matches('[data-report-mode],[data-fin-period],[data-fin-filter],[data-fin-page],[data-fin-receipt],#fin-xlsx,#fin-print'))return;
 e.preventDefault();e.stopImmediatePropagation();
 if(data.reportMode){financeSequence++;financeLoading=false;financeMode=data.reportMode;render();return;}
 if(data.finPeriod){financePreset(data.finPeriod);return;}
 if(data.finFilter){financeCategory=data.finFilter;financePage=1;financeUpdateLedger();$('#fin-ledger').scrollIntoView({behavior:'smooth',block:'start'});return;}
 if(data.finPage){financePage+=Number(data.finPage);financeUpdateLedger();return;}
 if(data.finReceipt){b.disabled=true;try{await liveLoad();openReceipt(Number(data.finReceipt));}catch(error){toast(error.message,'error');}finally{b.disabled=false;}return;}
 if(!financeMatches()||financeLoading)return;
 if(b.id==='fin-print'){const details=[...document.querySelectorAll('.fin-debts details')].map(d=>[d,d.open]);details.forEach(([d])=>d.open=true);document.body.classList.add('print-finance');const reset=()=>{document.body.classList.remove('print-finance');details.forEach(([d,open])=>d.open=open);};window.addEventListener('afterprint',reset,{once:true});window.print();return;}
 b.disabled=true;
 try{const r=await fetch('/api/reports.finance.export',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf,'X-App-Language':I18N.lang},body:JSON.stringify({start:financeData.start,end:financeData.end,revision:financeData.revision,category:financeCategory,query:financeQuery})});if(!r.ok)throw Error((await r.json()).error);const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`report-${financeData.start}-${financeData.end}.xlsx`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
 catch(error){toast(error.message,'error');}finally{b.disabled=false;}
},true);
if(liveSession&&liveData)render();
