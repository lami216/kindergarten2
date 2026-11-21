/* Saved attendance summaries share the existing register and roll-call flow. */
'use strict';
const attendanceOverviewPrefix='attendanceOverview.';
const AO=(key,values)=>I18N.tr(attendanceOverviewPrefix+key,values);
let attendanceOverviewPeriod='day',attendanceOverviewData=null,attendanceOverviewLoading=false,attendanceOverviewError='';
let attendanceOverviewSequence=0,attendanceOverviewKey='',attendanceOverviewOnScreen=false;
function attendanceOverviewKind(){return page==='student-attendance'?'students':page==='teacher-attendance'?'teachers':null;}
function attendanceOverviewScope(){
 const kind=attendanceOverviewKind();
 if(!kind||!liveSession||!attendanceState||attendanceState.kind!==kind||!personCan((kind==='students'?'student_attendance':'teacher_attendance')+'.view'))return null;
 const on=attendanceState.date,department=Number(attendanceState.department)||null;
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(on||'')))return null;
 return {kind,date:on,department_id:department,key:[liveSession.user.user_id,liveSession.user.auth_version,kind,on,department||''].join('|')};
}
function invalidateAttendanceOverview(){attendanceOverviewSequence++;attendanceOverviewData=null;attendanceOverviewLoading=false;attendanceOverviewError='';}
function attendanceOverviewRate(value){return value===null||value===undefined?'—':I18N.number(value)+'%';}
function attendanceOverviewHeader(){
 return `<div class="attendance-period-head"><h2>${AO('summary')}</h2><div class="choices attendance-periods" role="group" aria-label="${AO('period')}">${['day','week','month'].map(key=>`<button type="button" class="choice ${attendanceOverviewPeriod===key?'active':''}" data-attendance-period="${key}" aria-pressed="${attendanceOverviewPeriod===key}">${AO(key)}</button>`).join('')}</div></div>`;
}
function attendanceOverviewBody(){
 const header=attendanceOverviewHeader();
 if(attendanceOverviewLoading||!attendanceOverviewData&&!attendanceOverviewError)return header+`<p class="attendance-overview-message" role="status">${AO('loading')}</p>`;
 if(attendanceOverviewError)return header+`<div class="attendance-overview-message"><p role="alert">${AO('failed')}</p><button type="button" class="secondary small" data-attendance-overview-retry>${AO('retry')}</button></div>`;
 const period=attendanceOverviewData.periods[attendanceOverviewPeriod],summary=period.summary;
 const range=esc(I18N.date(period.start))+(period.start===period.end?'':' — '+esc(I18N.date(period.end)));
 const metric=(key,icon,label,value,accent,tint)=>stat(icon,AO(label),attendanceOverviewRate(value),'',accent,tint).replace('class="stat"',`class="stat attendance-overview-stat" data-overview-metric="${key}"`);
 return header+`<div class="attendance-overview-context"><span class="attendance-overview-range"><bdi dir="ltr">${range}</bdi></span><span>${AO('savedRecords',{count:I18N.number(summary.total)})} · ${AO('recordedDays',{count:I18N.number(period.recorded_days)})}</span></div><div class="stats attendance-overview-stats">${metric('present','✅','attendanceRate',summary.attendance_rate,'#26976a','#eef7f1')}${metric('absent','📌','absenceRate',summary.absence_rate,'#b45309','#fffbeb')}</div><div class="attendance-overview-counts">${['present','absent','excused'].map(key=>`<span>${AO(key)} <strong>${I18N.number(summary[key])}</strong></span>`).join('')}</div>${!summary.total?`<p class="attendance-overview-empty">${AO('empty')}</p>`:''}<p class="attendance-overview-method">${AO('method')}</p>`;
}
function paintAttendanceOverview(){const host=$('#attendance-overview');if(host)host.innerHTML=attendanceOverviewBody();}
function attendanceOverviewCurrent(identity,scope,version){
 if(version!==attendanceOverviewSequence)return false;
 const current=attendanceOverviewScope();
 if(identity===liveSession&&current?.key===scope.key)return true;
 invalidateAttendanceOverview();
 if(current){attendanceOverviewKey=current.key;paintAttendanceOverview();loadAttendanceOverview();}
 return false;
}
async function loadAttendanceOverview(){
 const scope=attendanceOverviewScope();if(!scope||attendanceOverviewLoading)return;
 const identity=liveSession,version=++attendanceOverviewSequence;
 attendanceOverviewLoading=true;attendanceOverviewError='';paintAttendanceOverview();
 try{
  const data=await liveCall('attendance.overview',{kind:scope.kind,date:scope.date,department_id:scope.department_id});
  if(!attendanceOverviewCurrent(identity,scope,version))return;
  if(data.kind!==scope.kind||data.date!==scope.date||String(data.department??'')!==String(scope.department_id??'')||!['day','week','month'].every(key=>data.periods?.[key]?.summary))throw Error('Invalid attendance summary');
  attendanceOverviewData=data;attendanceOverviewLoading=false;paintAttendanceOverview();
 }catch(error){
  if(!attendanceOverviewCurrent(identity,scope,version))return;
  attendanceOverviewData=null;attendanceOverviewLoading=false;attendanceOverviewError=error.message||'failed';paintAttendanceOverview();
 }
}
const attendanceOverviewOriginalBody=attendanceBody;
attendanceBody=function(){
 const original=attendanceOverviewOriginalBody();if(!attendanceOverviewKind())return original;
 const template=document.createElement('template');template.innerHTML=original;
 const button=template.content.querySelector('#start-attendance');if(!button||!attendanceState)return original;
 const rows=rollScope(),counts=rollCounts(rows),kind=attendanceState.kind;
 return `<div class="attendance-day-actions"><div><strong>${AO('dayRegister')}</strong><span>${AO(kind==='students'?'studentRoster':'teacherRoster',{count:I18N.number(rows.length)})}${counts.unmarked?` · ${AO('unmarked',{count:I18N.number(counts.unmarked)})}`:''}</span></div>${button.outerHTML}</div>`;
};
const attendanceOverviewOriginalShell=attendanceShell;
attendanceShell=function(kind){
 const html=attendanceOverviewOriginalShell(kind);if(!personCan((kind==='students'?'student_attendance':'teacher_attendance')+'.view'))return html;
 const template=document.createElement('template');template.innerHTML=html;
 template.content.querySelector('.page-heading p')?.remove();
 const setup=template.content.querySelector('.roll-setup');if(!setup)return html;
 setup.classList.add('attendance-workspace');
 setup.querySelector(':scope>.roll-step-label')?.remove();setup.querySelector(':scope>h2')?.remove();
 const filters=setup.querySelector(':scope>.person-filters');filters?.classList.remove('body-space');filters?.classList.add('attendance-overview-filters');
 const dateLabel=setup.querySelector('#attendance-date')?.closest('label');
 dateLabel?.childNodes.forEach(node=>{if(node.nodeType===Node.TEXT_NODE&&node.textContent.trim())node.textContent=I18N.tr('date.label');});
 setup.insertAdjacentHTML('beforeend',`<section id="attendance-overview" aria-live="polite">${attendanceOverviewBody()}</section>`);
 return template.innerHTML;
};
const attendanceOverviewRender=render;
render=function(...args){
 const scope=attendanceOverviewScope(),active=!!scope;
 if(!active&&attendanceOverviewOnScreen||active&&(!attendanceOverviewOnScreen||scope.key!==attendanceOverviewKey))invalidateAttendanceOverview();
 attendanceOverviewOnScreen=active;attendanceOverviewKey=scope?.key||'';
 const result=attendanceOverviewRender(...args);
 if(active&&!attendanceOverviewData&&!attendanceOverviewLoading&&!attendanceOverviewError)queueMicrotask(()=>{if(attendanceOverviewScope())loadAttendanceOverview();});
 return result;
};
const attendanceOverviewRead=loadAttendance;
loadAttendance=async function(...args){
 invalidateAttendanceOverview();paintAttendanceOverview();
 try{return await attendanceOverviewRead(...args);}
 finally{if(attendanceOverviewScope()&&!attendanceOverviewData&&!attendanceOverviewLoading&&!attendanceOverviewError)loadAttendanceOverview();}
};
const attendanceOverviewLoad=liveLoad;
liveLoad=async function(...args){try{return await attendanceOverviewLoad(...args);}finally{invalidateAttendanceOverview();paintAttendanceOverview();if(attendanceOverviewScope()&&$('#attendance-overview'))loadAttendanceOverview();}};
const attendanceOverviewLogin=liveLoginScreen;
liveLoginScreen=function(){invalidateAttendanceOverview();attendanceOverviewPeriod='day';attendanceOverviewKey='';attendanceOverviewOnScreen=false;return attendanceOverviewLogin();};
document.addEventListener('change',event=>{
 if(event.target.id!=='attendance-department'||!attendanceOverviewScope())return;
 invalidateAttendanceOverview();attendanceOverviewKey=attendanceOverviewScope().key;loadAttendanceOverview();
});
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-attendance-period],[data-attendance-overview-retry]'),kind=attendanceOverviewKind();
 if(!button||!kind||!personCan((kind==='students'?'student_attendance':'teacher_attendance')+'.view'))return;
 event.preventDefault();event.stopImmediatePropagation();
 if(button.hasAttribute('data-attendance-overview-retry')){invalidateAttendanceOverview();loadAttendanceOverview();return;}
 const period=button.dataset.attendancePeriod;if(!['day','week','month'].includes(period))return;
 attendanceOverviewPeriod=period;paintAttendanceOverview();
 if(!attendanceOverviewData&&!attendanceOverviewLoading&&!attendanceOverviewError)loadAttendanceOverview();
},true);
if(liveSession&&liveData&&attendanceOverviewKind())render();
