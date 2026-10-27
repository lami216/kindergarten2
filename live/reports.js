/* One reports page; dates and export always refer to the displayed snapshot. */
'use strict';
const RP=k=>I18N.tr(`reports.${k}`);
let financeMode='finance',financeData=null,financeLoading=false,financeSequence=0,financeCategory='all',financeQuery='',financePage=1;
let financeDates=null;
let schoolTab='attendance',schoolQuery='',schoolPage=1;
let financeSection='overview',reportCustom=false,reportPreset='thisMonth',reportAuto=false,attendanceFilter='all';
let schoolQueries={new:'',attendance:''},schoolPages={new:1,attendance:1};
function schoolRate(value){return value===null||value===undefined?'—':I18N.number(value)+'%';}
function reportDelta(key,current,old,kind='money'){
 if(current===null||current===undefined||old===null||old===undefined)return `<small class="report-delta">${RP('noComparison')}</small>`;
 const difference=Math.round((Number(current)-Number(old))*10)/10;
 if(!difference)return `<small class="report-delta">${RP('unchanged')}</small>`;
 const value=kind==='money'?money(Math.abs(difference)):I18N.number(Math.abs(difference));
 return `<small class="report-delta"><bdi dir="ltr">${difference>0?'↑':'↓'} ${value}</bdi> ${kind==='money'?'':RP(kind==='points'?'points':'pupilsUnit')} · ${RP('vsPrevious')}</small>`;
}
function reportMetric(title,value,icon,target,foot='',extra=''){
 return `<button type="button" class="report-metric" data-report-section="${target}" ${extra}><span class="report-metric-label"><span class="report-icon">${icon}</span>${RP(title)}<span class="report-open" aria-hidden="true">↗</span></span><strong><bdi dir="ltr">${value}</bdi></strong>${foot}</button>`;
}
function reportOverview(){
 const r=financeData,s=r.summary,school=r.school,a=school?.attendance,previous=r.comparison;
 const absentees=a?.items.filter(row=>row.absent+row.excused>0).length||0;
 return `<div class="report-overview-grid"><section class="panel report-group"><div class="person-section-head"><h2>${RP('finance')}</h2><button class="link-button" data-report-section="money">${RP('viewMovements')} ←</button></div><div class="fin-cards">${financeCard('income',s.income,'income','↙')}${financeCard('outgoing',s.outgoing,'outgoing','↗')}${financeCard('net',s.net,'all','＝')}</div></section>${school?`<section class="panel report-group"><div class="person-section-head"><h2>${RP('schoolTitle')}</h2></div><div class="school-cards">${reportMetric('newStudents',I18N.number(school.new_count),'🎒',r.permissions.students?'new':'overview',reportDelta('new',school.new_count,previous?.new_count,'students'))}${a?reportMetric('attendance_rate',schoolRate(a.summary.attendance_rate),'✅','attendance',reportDelta('attendance',a.summary.attendance_rate,previous?.attendance?.attendance_rate,'points'))+reportMetric('childrenWithAbsence',I18N.number(absentees),'📌','attendance',`<small>${I18N.tr('reports.ofMarked',{count:a.students_count})}</small>`,'data-attendance-filter="absence"'):''}</div></section>`:''}</div>${previous?`<div class="report-comparison-note"><span>↔ ${RP('previousRange')}: <bdi dir="ltr">${esc(I18N.date(previous.start))} — ${esc(I18N.date(previous.end))}</bdi></span><small>${RP('comparisonNote')}</small></div>`:''}<details class="report-help"><summary>${RP('understandSummary')}</summary><p>${RP('cashNote')}</p><p>${RP('registrationNote')}</p>${a?`<p>${RP('attendanceNote')}</p>`:''}</details>`;
}
function reportMoney(){
 const r=financeData,s=r.summary;
 return `<section class="report-group"><div class="fin-cards">${financeCard('income',s.income,'income','↙')}${financeCard('outgoing',s.outgoing,'outgoing','↗')}${financeCard('net',s.net,'all','＝')}</div></section><section class="panel"><div class="person-section-head"><h2>${RP('details')}</h2><span class="muted">${I18N.tr('reports.count',{count:r.items.length})}</span></div><div class="fin-detail-controls fin-controls"><label>${RP('query')}<input id="fin-query" maxlength="120" value="${esc(financeQuery)}" placeholder="${RP('queryHint')}"></label><label>${RP('type')}<select id="fin-category">${['all','income','outgoing','operational','salary','advance'].map(k=>`<option value="${k}" ${k===financeCategory?'selected':''}>${RP(k)}</option>`).join('')}</select></label></div><p class="muted report-caption">${RP('filterNote')}</p><div id="fin-ledger">${financeLedger()}</div></section><div class="fin-breakdowns"><details class="panel report-breakdown"><summary>${RP('incomeBreakdown')}</summary>${['registration','gilet','monthly',...(Number(s.other_income)?['other_income']:[])].map(k=>detailLine(RP(k),money(s[k]))).join('')}<small>${RP('prepaid')}: ${money(s.prepaid)}. ${RP('partNote')}</small></details><details class="panel report-breakdown"><summary>${RP('expenseBreakdown')}</summary>${['operational','salary','advance'].map(k=>detailLine(RP(k),money(s[k]))).join('')}</details></div><details class="panel report-advanced"><summary>${RP('balancesAndDebt')}</summary><div class="fin-balances"><span>${RP('opening')} <strong>${money(s.opening)}</strong></span><span>${RP('closing')} <strong>${money(s.closing)}</strong></span></div><p class="muted">${RP('cashNote')}</p><div class="fin-debts">${financeDebt('students','studentsDebt','payments')}${financeDebt('suppliers','suppliersDebt','expenses')}</div><p class="muted">${RP('debtNote')}</p></details>`;
}
function financeSchool(){
 const school=financeData.school,attendance=financeSection==='attendance',a=school.attendance;
 schoolTab=attendance?'attendance':'new';
 return `<section class="panel school-period"><div class="person-section-head"><h2>${RP(attendance?'attendanceDetails':'newStudents')}</h2><span class="report-count">${I18N.tr('reports.studentCount',{count:attendance?a.students_count:school.new_count})}</span></div>${attendance?`<div class="attendance-totals">${['present','absent','excused'].map(k=>`<div><span>${RP(k)}</span><strong>${I18N.number(a.summary[k])}</strong></div>`).join('')}</div><div class="attendance-context"><span>${RP('attendance_rate')}: <b>${schoolRate(a.summary.attendance_rate)}</b></span><span>${RP('absence_rate')}: <b>${schoolRate(a.summary.absence_rate)}</b></span><span>${RP('recordedDays')}: <b>${I18N.number(a.recorded_days)}</b></span></div>`:''}<div class="school-filters fin-controls"><label>${RP('studentSearch')}<input id="school-query" maxlength="120" value="${esc(schoolQuery)}"></label>${attendance?`<label>${RP('showStudents')}<select id="school-status">${['all','absence','unexcused','excused'].map(k=>`<option value="${k}" ${attendanceFilter===k?'selected':''}>${RP('attendanceFilter.'+k)}</option>`).join('')}</select></label>`:''}</div><div id="school-details">${schoolDetails()}</div><details class="report-help"><summary>${RP(attendance?'attendanceMethod':'registrationMethod')}</summary><p>${RP(attendance?'attendanceNote':'registrationNote')}</p>${!attendance&&school.unknown_dates?`<p>${I18N.tr('reports.unknownDates',{count:school.unknown_dates})}</p>`:''}</details></section>`;
}
function reportSectionTitle(){return RP({overview:'overview',money:'moneyTab',new:'newStudents',attendance:'attendanceTab'}[financeSection]);}
function reportSectionHTML(){
 if(financeSection==='new'&&!financeData.permissions.students||financeSection==='attendance'&&!financeData.school?.attendance)financeSection='overview';
 return financeSection==='overview'?reportOverview():financeSection==='money'?reportMoney():financeSchool();
}
function reportGo(section,filter){
 if(financeSection==='new'||financeSection==='attendance'){schoolQueries[schoolTab]=schoolQuery;schoolPages[schoolTab]=schoolPage;}
 financeSection=section;
 if(section==='new'||section==='attendance'){schoolTab=section;schoolQuery=schoolQueries[section];schoolPage=schoolPages[section];if(filter){attendanceFilter=filter;schoolPage=1;}}
 const el=$('#report-section');if(el){el.innerHTML=reportSectionHTML();$('#print-section-title').textContent=reportSectionTitle();document.querySelectorAll('[data-report-section][role="tab"]').forEach(b=>{b.classList.toggle('active',b.dataset.reportSection===financeSection);b.setAttribute('aria-selected',String(b.dataset.reportSection===financeSection));b.tabIndex=b.dataset.reportSection===financeSection?0:-1;});}
}

function schoolDetails(){
 const school=financeData.school;if(!school)return '';
 if(!school.attendance)schoolTab='new';else if(!financeData.permissions.students)schoolTab='attendance';
 const attendance=schoolTab==='attendance',q=schoolQuery.trim().normalize('NFKC').toLowerCase();
 const rows=(attendance?school.attendance.items:school.new_students).filter(r=>!attendance||attendanceFilter==='all'||attendanceFilter==='absence'&&r.absent+r.excused>0||attendanceFilter==='unexcused'&&r.absent>0||attendanceFilter==='excused'&&r.excused>0).filter(r=>[r.name,r.department||''].join(' ').normalize('NFKC').toLowerCase().includes(q));
 const pages=Math.max(1,Math.ceil(rows.length/15));schoolPage=Math.min(schoolPage,pages);
 const headers=attendance?['student','present','absent','excused','total','attendance_rate','absence_rate']:['student','registeredOn','department','fileState'];
 const table=(items,extra)=>`<div class="table-wrap school-table ${extra}"><table><thead><tr>${headers.map(k=>`<th>${RP(k)}</th>`).join('')}</tr></thead><tbody>${items.map(r=>{const student=students.find(s=>s.id===r.id);return `<tr><td><div class="row-person">${student?studentAvatar(student):''}<div><strong>${esc(r.name)}</strong><small>${r.archived?RP('archived'):'#'+esc(r.id.slice(-6))}</small></div></div></td>${(attendance?['present','absent','excused','total','attendance_rate','absence_rate']:['registered_on','department','archived']).map(k=>`<td data-label="${RP(k==='registered_on'?'registeredOn':k==='archived'?'fileState':k)}">${k.endsWith('_rate')?schoolRate(r[k]):k==='registered_on'?esc(I18N.date(r[k])):k==='archived'?(r[k]?RP('archived'):RP('active')):esc(r[k]??'—')}</td>`).join('')}</tr>`;}).join('')}</tbody></table></div>`;
 return `<p class="muted report-caption">${I18N.tr('reports.studentCount',{count:rows.length})}</p>${rows.length?table(rows.slice((schoolPage-1)*15,schoolPage*15),'school-screen-table'): `<p class="empty">${RP(attendance?'noAttendance':'noNewStudents')}</p>`}${table(rows,'school-print-table')}<div class="pager fin-controls"><button class="secondary" data-school-page="-1" ${schoolPage===1?'disabled':''}>${RP('previous')}</button><span>${schoolPage} / ${pages}</span><button class="secondary" data-school-page="1" ${schoolPage===pages?'disabled':''}>${RP('next')}</button></div>`;
}
function refreshSchool(){const el=$('#school-details');if(el)el.innerHTML=schoolDetails();document.querySelectorAll('[data-school-tab]').forEach(b=>b.classList.toggle('active',b.dataset.schoolTab===schoolTab));}
document.addEventListener('input',e=>{if(e.target.id==='school-query'){schoolQuery=e.target.value;schoolPage=1;refreshSchool();}});
document.addEventListener('click',e=>{const b=e.target.closest('[data-school-page]');if(!b)return;e.preventDefault();schoolPage+=Number(b.dataset.schoolPage);refreshSchool();});
document.addEventListener('change',e=>{if(e.target.id==='school-status'){attendanceFilter=e.target.value;schoolPage=1;refreshSchool();}});
function financeAllowed(){return !!liveSession&&(demoActor.admin||liveSession.user.permissions.includes('reports.view'));}
const reportsMayPage=demoMayPage;
demoMayPage=function(target){return target==='reports'?financeAllowed():reportsMayPage(target);};
function financeHasOther(){return ['students','receipts','expenses','salaries'].some(area=>demoCan(area));}
function financeDefaults(){return financeDates||(financeDates={start:today.slice(0,8)+'01',end:today});}
function financeRange(){return {start:$('#fin-start')?.value||'',end:$('#fin-end')?.value||''};}
function financeMatches(){const v=financeRange();return !!financeData&&v.start===financeData.start&&v.end===financeData.end;}
function financePageHTML(){
 const dates=financeDefaults();if(!financeHasOther())financeMode='finance';
 const action=financeMode==='other'?`<button class="secondary small" data-report-mode="finance">${RP('backOverview')}</button>`:financeHasOther()?`<button class="secondary small" data-report-mode="other">${RP('other')}</button>`:'';
 return `<div id="finance-page">${heading(RP('title'),RP('subtitle'),action)}${financeMode==='other'?reportScreen():`<form id="finance-report-form" class="panel report-period fin-controls"><div class="report-period-title"><div class="report-period-caption"><span class="report-period-icon" aria-hidden="true">📅</span><h2>${RP('choosePeriod')}</h2></div><strong id="report-range"><bdi dir="ltr">${esc(I18N.date(dates.start))} — ${esc(I18N.date(dates.end))}</bdi></strong></div><div class="fin-dates" ${reportCustom?'':'hidden'}><label>${RP('from')}<input type="date" id="fin-start" name="start" required max="${today}" value="${esc(dates.start)}"></label><label>${RP('to')}<input type="date" id="fin-end" name="end" required max="${today}" value="${esc(dates.end)}"></label></div><div class="report-period-actions"><div class="fin-presets">${['thisMonth','lastMonth','last7','today','custom'].map(k=>`<button type="button" class="secondary small ${reportPreset===k?'active':''}" data-fin-period="${k}" ${k==='custom'?`aria-expanded="${reportCustom}"`:''}>${RP(k)}</button>`).join('')}</div><button class="primary" ${financeLoading?'disabled':''}>${financeLoading?RP('pending'):RP('show')}</button></div><p class="error" role="alert"></p></form><section id="finance-output" aria-live="polite">${financeOutput()}</section>`}</div>`;
}

function financeCard(key,value,filter,icon){return `<button type="button" class="fin-card ${key}-card" data-fin-filter="${filter}" aria-pressed="${financeSection==='money'&&financeCategory===filter}"><span class="report-metric-label"><span class="report-icon">${({income:'💵',outgoing:'📦',net:'💰'})[key]||icon}</span>${RP(key)}<span class="report-open" aria-hidden="true">↗</span></span><strong><bdi dir="ltr">${money(value)}</bdi> <small>${RP('currency')}</small></strong>${reportDelta(key,value,financeData?.comparison?.summary[key])}</button>`;}

function financeOutput(){
 if(financeLoading)return `<div class="panel report-loading" role="status">${RP('pending')}</div>`;
 if(!financeData)return `<div class="panel empty" role="status">${RP('empty')}</div>`;
 const r=financeData,tabs=[['overview','overview','◫'],['money','moneyTab','↕'],...(r.permissions.students?[['new','newStudents','🎒']]:[]),...(r.school?.attendance?[['attendance','attendanceTab','✓']]:[])];
 if(!tabs.some(([key])=>key===financeSection))financeSection='overview';
 return `<div class="report-section-bar fin-controls"><div class="report-nav fin-controls" role="tablist" aria-label="${RP('reportSections')}">${tabs.map(([key,label,icon])=>`<button type="button" role="tab" id="report-tab-${key}" aria-controls="report-section" aria-selected="${financeSection===key}" tabindex="${financeSection===key?0:-1}" class="${financeSection===key?'active':''}" data-report-section="${key}" ${key==='new'||key==='attendance'?`data-school-tab="${key}"`:''}><span>${icon}</span>${RP(label)}</button>`).join('')}</div><div class="actions fin-export-actions"><button class="secondary small" id="fin-xlsx">↓ ${RP('xlsx')}</button><button class="secondary small" id="fin-print">${RP('printSection')}</button></div></div><p class="muted report-generated fin-controls">${RP('generated')} ${esc(new Date(r.generated_at).toLocaleString(I18N.lang==='fr'?'fr-FR':'ar-MR'))}</p><div class="report-print-heading"><h2 id="print-section-title">${reportSectionTitle()}</h2><p><bdi dir="ltr">${esc(I18N.date(r.start))} — ${esc(I18N.date(r.end))}</bdi></p></div><div id="report-section" role="tabpanel" aria-labelledby="report-tab-${financeSection}">${reportSectionHTML()}</div>`;
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
function financeUpdateLedger(){const block=$('#fin-ledger');if(block)block.innerHTML=financeLedger();if($('#fin-category'))$('#fin-category').value=financeCategory;document.querySelectorAll('[data-fin-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.finFilter===financeCategory)));}
async function loadFinance(form){
 if(!financeAllowed()||!form.reportValidity())return;
 const dates=financeRange();if(dates.start>dates.end){form.querySelector('.error').textContent=I18N.sourceLabel('راجع تاريخ البداية والنهاية.');return;}
 const version=++financeSequence,identity=liveSession;financeDates=dates;financeData=null;financeLoading=true;$('#finance-output').innerHTML=financeOutput();form.querySelector('button.primary').disabled=true;
 try{const result=await liveCall('reports.finance',dates);if(version!==financeSequence||liveSession!==identity||page!=='reports'||financeMode!=='finance')return;financeData=result;financePage=1;schoolPage=1;financeLoading=false;$('#finance-output').innerHTML=financeOutput();toast(RP('saved'));}
 catch(e){if(version===financeSequence&&page==='reports'){form.querySelector('.error').textContent=e.message;$('#finance-output').innerHTML='';}}
 finally{if(version===financeSequence){financeLoading=false;if(form.isConnected)form.querySelector('button.primary').disabled=false;}}
}
function financePreset(name){
 if(name==='custom'){reportCustom=!reportCustom;reportPreset='custom';$('.fin-dates').hidden=!reportCustom;document.querySelector('[data-fin-period=custom]').setAttribute('aria-expanded',String(reportCustom));document.querySelectorAll('[data-fin-period]').forEach(b=>b.classList.toggle('active',b.dataset.finPeriod==='custom'));if(reportCustom)$('#fin-start').previousElementSibling?.querySelector('input')?.focus();return;}
 const now=new Date(today+'T12:00:00'),format=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
 let start=today,end=today;
 if(name==='last7'){now.setDate(now.getDate()-6);start=format(now);}
 if(name==='thisMonth')start=today.slice(0,8)+'01';
 if(name==='lastMonth'){now.setDate(0);end=format(now);now.setDate(1);start=format(now);}
 reportPreset=name;document.querySelectorAll('[data-fin-period]').forEach(b=>b.classList.toggle('active',b.dataset.finPeriod===name));$('#fin-start').value=start;$('#fin-end').value=end;$('#report-range').textContent=I18N.date(start)+' — '+I18N.date(end);loadFinance($('#finance-report-form'));
}
function otherReportFields(){const f=$('#report-form');if(!f)return;const kind=f.elements.kind.value;for(const name of ['start','end','teacher']){const el=f.elements[name],visible=name==='teacher'?kind==='salaries':name==='start'?!['students','debt'].includes(kind):kind!=='students';el.closest('label').hidden=!visible;el.disabled=!visible;if(name!=='teacher')el.required=visible;}const opt=f.querySelector('[name="kind"] option[value="expenses"]');if(opt)opt.textContent=RP('invoiceReport');let note=$('#fin-invoice-note');if(!note){note=document.createElement('p');note.id='fin-invoice-note';note.className='muted';f.append(note);}note.textContent=kind==='expenses'?RP('invoiceNote'):'';}
const reportsRender=render;
render=function(){
 if(page==='tools'&&toolTab==='reports'&&financeAllowed()){page='reports';financeMode='other';}
 if(page==='reports'&&financeAllowed()){
  $('#crumb').textContent=RP('title');$('#content').innerHTML=financePageHTML();document.querySelectorAll('nav [data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page==='reports');b.setAttribute('aria-current',b.dataset.page==='reports'?'page':'false');});
  if(financeMode==='other'){const option=$('#report-form option[value="finance"]');option?.remove();otherReportFields();if(!teacherOptions.length&&demoCan('salaries'))liveCall('teachers.options').then(options=>{teacherOptions=options;const f=$('#report-form');if(f)f.elements.teacher.innerHTML=reportTeacherChoices(f.elements.teacher.value);}).catch(e=>toast(e.message,'error'));}
  if(financeMode==='finance'&&reportAuto){reportAuto=false;const form=$('#finance-report-form');queueMicrotask(()=>{if(form?.isConnected)loadFinance(form);});}
 }else reportsRender();
 if(financeAllowed()&&!$('#nav-reports')){const b=document.createElement('button');b.id='nav-reports';b.dataset.page='reports';b.innerHTML='📋 <span>'+RP('title')+'</span>';b.onclick=()=>{financeMode='finance';financeSection='overview';reportAuto=true;navigate('reports');};document.querySelector('nav').insertBefore(b,$('#nav-workspace')||$('#demo-logout'));}
 if(!financeAllowed())$('#nav-reports')?.remove();
};
const reportsLogin=liveLoginScreen;
liveLoginScreen=function(){financeSequence++;financeData=null;financeDates=null;financeQuery='';financeCategory='all';financeLoading=false;schoolQuery='';schoolPage=1;schoolTab='attendance';financeSection='overview';reportCustom=false;reportPreset='thisMonth';reportAuto=false;attendanceFilter='all';schoolQueries={new:'',attendance:''};schoolPages={new:1,attendance:1};$('#nav-reports')?.remove();reportsLogin();};
const reportsSubmit=liveSubmit;
liveSubmit=async function(form){if(form.id==='finance-report-form')return loadFinance(form);return reportsSubmit(form);};
const reportsSaved=liveSaved;
liveSaved=async function(...args){const result=await reportsSaved(...args);financeSequence++;financeData=null;return result;};
document.addEventListener('input',e=>{if(e.target.id==='fin-start'||e.target.id==='fin-end'){financeSequence++;financeData=null;financeLoading=false;financeDates=financeRange();reportPreset='custom';$('#report-range').textContent=financeDates.start&&financeDates.end?I18N.date(financeDates.start)+' — '+I18N.date(financeDates.end):RP('custom');$('#finance-output').innerHTML=`<div class="panel" role="status">${RP('stale')}</div>`;$('#finance-report-form button.primary').disabled=false;}if(e.target.id==='fin-query'){financeQuery=e.target.value;financePage=1;financeUpdateLedger();}});
document.addEventListener('change',e=>{if(e.target.id==='fin-category'){financeCategory=e.target.value;financePage=1;financeUpdateLedger();}if(e.target.matches('#report-form [name="kind"]'))otherReportFields();});
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;const data=b.dataset;
 if(!b.matches('[data-report-mode],[data-report-section],[data-fin-period],[data-fin-filter],[data-fin-page],[data-fin-receipt],#fin-xlsx,#fin-print'))return;
 e.preventDefault();e.stopImmediatePropagation();
 if(data.reportSection){reportGo(data.reportSection,data.attendanceFilter);$('#report-section').setAttribute('aria-labelledby','report-tab-'+financeSection);return;}
 if(data.reportMode){financeSequence++;financeLoading=false;financeMode=data.reportMode;reportAuto=financeMode==='finance';render();return;}
 if(data.finPeriod){financePreset(data.finPeriod);return;}
 if(data.finFilter){financeCategory=data.finFilter;financePage=1;reportGo('money');$('#report-section').setAttribute('aria-labelledby','report-tab-money');financeUpdateLedger();$('#fin-ledger').scrollIntoView({behavior:'smooth',block:'start'});return;}
 if(data.finPage){financePage+=Number(data.finPage);financeUpdateLedger();return;}
 if(data.finReceipt){b.disabled=true;try{await liveLoad();openReceipt(Number(data.finReceipt));}catch(error){toast(error.message,'error');}finally{b.disabled=false;}return;}
 if(!financeMatches()||financeLoading)return;
 if(b.id==='fin-print'){const details=[...document.querySelectorAll('#report-section details')].map(d=>[d,d.open]);details.forEach(([d])=>d.open=true);document.body.classList.add('print-finance');const reset=()=>{document.body.classList.remove('print-finance');details.forEach(([d,open])=>d.open=open);};window.addEventListener('afterprint',reset,{once:true});window.print();return;}
 b.disabled=true;
 try{const r=await fetch('/api/reports.finance.export',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf,'X-App-Language':I18N.lang},body:JSON.stringify({start:financeData.start,end:financeData.end,revision:financeData.revision,category:financeSection==='money'?financeCategory:'all',query:financeSection==='money'?financeQuery:''})});if(!r.ok)throw Error((await r.json()).error);const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=`report-${financeData.start}-${financeData.end}.xlsx`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
 catch(error){toast(error.message,'error');}finally{b.disabled=false;}
},true);
document.addEventListener('keydown',e=>{const button=e.target.closest('.report-nav [role=tab]');if(!button)return;const tabs=[...document.querySelectorAll('.report-nav [role=tab]')],index=tabs.indexOf(button),direction=I18N.lang==='ar'?-1:1;let next;if(e.key==='Home')next=0;else if(e.key==='End')next=tabs.length-1;else if(e.key==='ArrowRight')next=(index+direction+tabs.length)%tabs.length;else if(e.key==='ArrowLeft')next=(index-direction+tabs.length)%tabs.length;else return;e.preventDefault();tabs[next].click();tabs[next].focus();});
if(liveSession&&liveData)render();
