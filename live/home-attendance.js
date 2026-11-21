/* The home page reads today's saved attendance without opening a roll call. */
'use strict';
const homeAttendancePrefix='homeAttendance.';
const HA=(key,values)=>I18N.tr(homeAttendancePrefix+key,values);
let homeAttendanceData=null,homeAttendanceLoading=false,homeAttendanceError='';
let homeAttendanceSequence=0,homeAttendanceOnScreen=false,homeAttendancePermissionKey='';
let homeAttendanceTimer=null,homeAttendanceMidnightDate=null;
const homeAttendanceActive=()=>!!liveSession&&!!liveData&&page==='dashboard';
const homeAttendanceCan=kind=>!!liveSession&&(liveSession.user.is_admin||liveSession.user.permissions.includes((kind==='students'?'student_attendance':'teacher_attendance')+'.view'));
const homeAttendanceAllowed=()=>homeAttendanceCan('students')||homeAttendanceCan('teachers');
const homeAttendancePermissions=()=>[liveSession?.user.user_id,liveSession?.user.auth_version,...['students','teachers'].map(kind=>homeAttendanceCan(kind)?kind:'')].join('|');
function invalidateHomeAttendance(){
 if(homeAttendanceTimer!==null)clearTimeout(homeAttendanceTimer);
 homeAttendanceTimer=null;homeAttendanceSequence++;
 homeAttendanceData=null;homeAttendanceLoading=false;homeAttendanceError='';
}
function homeAttendanceNumber(value){return I18N.number(Number(value||0));}
function homeAttendanceRate(value){return value===null||value===undefined||!Number.isFinite(Number(value))?'—':I18N.number(Number(value))+'%';}
function homeAttendanceCard(kind,summary){
 const studentsMode=kind==='students',roster=Number(summary.roster_total||0),marked=Number(summary.total||0),unmarked=Number(summary.unmarked||0);
 const state=!roster?'empty':!marked?'notRecorded':summary.complete?'complete':'incomplete';
 const absent=Number(summary.absent||0)+Number(summary.excused||0);
 const progress=roster?`${HA('recorded',{marked:homeAttendanceNumber(marked),total:homeAttendanceNumber(roster)})}${unmarked?` · ${HA('unmarked',{count:homeAttendanceNumber(unmarked)})}`:''}`:HA(studentsMode?'noStudents':'noTeachers');
 return `<button type="button" class="stat home-attendance-card" style="--accent:${studentsMode?'#26976a':'#0369a1'};--tint:${studentsMode?'#eef7f1':'#e0f2fe'}" data-home-attendance-kind="${kind}" data-person-nav="${studentsMode?'student-attendance':'teacher-attendance'}"><span class="stat-heading"><span class="stat-icon" aria-hidden="true">${studentsMode?'🎒':'👨‍🏫'}</span><span class="stat-label">${HA(studentsMode?'studentsAttendance':'teachersAttendance')}</span><span class="home-attendance-open" aria-hidden="true">↗</span></span><span class="stat-number home-attendance-stat present"><strong class="stat-value"><bdi dir="ltr">${homeAttendanceRate(summary.attendance_rate)}</bdi></strong><span class="stat-unit"><small>${HA('present')}</small><b class="home-attendance-count">${homeAttendanceNumber(summary.present)}</b></span></span><span class="home-attendance-stat absent" title="${HA('excused',{count:homeAttendanceNumber(summary.excused)})}"><span><small>${HA('absent')}</small><b class="home-attendance-count">${homeAttendanceNumber(absent)}</b></span><strong><bdi dir="ltr">${homeAttendanceRate(summary.absence_rate)}</bdi></strong></span><span class="home-attendance-progress"><span class="home-attendance-state ${state}">${progress}</span></span></button>`;
}
function homeAttendanceBody(){
 const header=`<div class="section-top home-attendance-head"><h2 id="home-attendance-title">${HA('title')}</h2>${homeAttendanceData?.date?`<time datetime="${esc(homeAttendanceData.date)}"><bdi dir="ltr">${esc(I18N.date(homeAttendanceData.date))}</bdi></time>`:''}</div>`;
 if(homeAttendanceLoading||!homeAttendanceData&&!homeAttendanceError)return header+`<div class="panel home-attendance-message" role="status">${HA('loading')}</div>`;
 if(homeAttendanceError)return header+`<div class="panel home-attendance-message"><p role="alert">${HA('failed')}</p><button type="button" class="secondary small" data-home-attendance-retry>${HA('retry')}</button></div>`;
 const cards=['students','teachers'].filter(kind=>homeAttendanceCan(kind)&&homeAttendanceData[kind]).map(kind=>homeAttendanceCard(kind,homeAttendanceData[kind]));
 if(!cards.length)return '';
 return header+`<div class="home-attendance-grid">${cards.join('')}</div><p class="home-attendance-method">${HA('rateHint')}</p>`;
}
function paintHomeAttendance(){
 let host=$('#home-attendance');
 if(!homeAttendanceActive()||!homeAttendanceAllowed()){host?.remove();return;}
 // Restricted home renders its welcome directly, without calling dashboard.
 // Mount only this authorized summary; never rebuild the financial dashboard.
 if(!host){
  const content=$('#content');if(!content)return;
  host=document.createElement('section');host.id='home-attendance';host.className='home-attendance body-space';
  host.setAttribute('aria-labelledby','home-attendance-title');host.setAttribute('aria-live','polite');content.append(host);
 }
 const body=homeAttendanceBody();host.hidden=!body;host.innerHTML=body;
}
function scheduleHomeAttendanceMidnight(){
 if(homeAttendanceTimer!==null)clearTimeout(homeAttendanceTimer);homeAttendanceTimer=null;
 const day=homeAttendanceData?.date;
 if(!day||!homeAttendanceActive()||!homeAttendanceAllowed())return;
 const suggested=Number(homeAttendanceData.refresh_after_ms);
 const delay=Number.isFinite(suggested)&&suggested>=1000?Math.min(86401000,suggested):60000;
 if(homeAttendanceMidnightDate===day&&delay<=60000)return;
 // A fresh long server delay resolves an early boundary refresh and arms the
 // real next midnight, including a later focus close to that midnight.
 if(delay>60000)homeAttendanceMidnightDate=null;
 const version=homeAttendanceSequence,identity=liveSession;
 // The server supplies a relative delay to its next business midnight. The
 // browser's clock must not bring the refresh forward or postpone it. The
 // per-day guard also bounds retries against older/test servers.
 homeAttendanceTimer=setTimeout(()=>{
  homeAttendanceTimer=null;
  if(version!==homeAttendanceSequence||identity!==liveSession||!homeAttendanceActive()||!homeAttendanceAllowed()||document.visibilityState==='hidden')return;
  homeAttendanceMidnightDate=day;refreshHomeAttendance();
 },delay);
}
function homeAttendanceRequestCurrent(identity,permissions,version){
 if(version!==homeAttendanceSequence)return false;
 if(identity===liveSession&&permissions===homeAttendancePermissions()&&homeAttendanceActive()&&homeAttendanceAllowed())return true;
 // Reauthentication can replace the session while a read is in flight. Drop
 // the old response and start a fresh read in the new authorized context.
 invalidateHomeAttendance();
 if(homeAttendanceActive()&&homeAttendanceAllowed()){
  homeAttendancePermissionKey=homeAttendancePermissions();paintHomeAttendance();loadHomeAttendance();
 }else $('#home-attendance')?.remove();
 return false;
}
async function loadHomeAttendance(){
 if(!homeAttendanceActive()||!homeAttendanceAllowed()||homeAttendanceLoading)return;
 const identity=liveSession,permissions=homeAttendancePermissions(),version=++homeAttendanceSequence;
 homeAttendanceLoading=true;homeAttendanceError='';paintHomeAttendance();
 try{
  const result=await liveCall('attendance.daily',{});
  if(!homeAttendanceRequestCurrent(identity,permissions,version))return;
  homeAttendanceData=result;
  if(/^\d{4}-\d{2}-\d{2}$/.test(String(result.date||'')))attendanceToday=result.date;
  homeAttendanceLoading=false;paintHomeAttendance();scheduleHomeAttendanceMidnight();
 }catch(error){
  if(!homeAttendanceRequestCurrent(identity,permissions,version))return;
  homeAttendanceData=null;homeAttendanceLoading=false;homeAttendanceError=error.message||'failed';paintHomeAttendance();
 }
}
function refreshHomeAttendance(){
 if(!homeAttendanceActive()||!homeAttendanceAllowed()||homeAttendanceLoading)return;
 invalidateHomeAttendance();loadHomeAttendance();
}
const homeAttendanceDashboard=dashboard;
dashboard=function(){
 const html=homeAttendanceDashboard();if(!homeAttendanceAllowed())return html;
 const template=document.createElement('template');template.innerHTML=html;
 const section=`<section id="home-attendance" class="home-attendance body-space" aria-labelledby="home-attendance-title" aria-live="polite">${homeAttendanceBody()}</section>`;
 const recent=template.content.querySelector('.two-col');
 if(recent)recent.insertAdjacentHTML('beforebegin',section);else template.content.append(document.createRange().createContextualFragment(section));
 return template.innerHTML;
};
const homeAttendanceRender=render;
render=function(...args){
 const active=homeAttendanceActive()&&homeAttendanceAllowed(),permissions=homeAttendancePermissions();
 if(!active&&homeAttendanceOnScreen||active&&(!homeAttendanceOnScreen||permissions!==homeAttendancePermissionKey))invalidateHomeAttendance();
 homeAttendanceOnScreen=active;homeAttendancePermissionKey=permissions;
 const result=homeAttendanceRender(...args);
 if(active){
  paintHomeAttendance();
  if(!homeAttendanceData&&!homeAttendanceLoading&&!homeAttendanceError)queueMicrotask(()=>{if(homeAttendanceActive()&&homeAttendanceAllowed()&&!homeAttendanceData&&!homeAttendanceError)loadHomeAttendance();});
 }
 return result;
};
const homeAttendanceLoad=liveLoad;
liveLoad=async function(...args){
 try{return await homeAttendanceLoad(...args);}
 finally{
  invalidateHomeAttendance();
  if(homeAttendanceActive()&&homeAttendanceAllowed()&&$('#home-attendance')){
   homeAttendanceOnScreen=true;homeAttendancePermissionKey=homeAttendancePermissions();paintHomeAttendance();loadHomeAttendance();
  }
 }
};
const homeAttendanceLogin=liveLoginScreen;
liveLoginScreen=function(){
 invalidateHomeAttendance();homeAttendanceOnScreen=false;homeAttendancePermissionKey='';homeAttendanceMidnightDate=null;
 $('#home-attendance')?.remove();return homeAttendanceLogin();
};
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-home-attendance-retry]');if(!button)return;
 event.preventDefault();event.stopImmediatePropagation();refreshHomeAttendance();
},true);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refreshHomeAttendance();});
window.addEventListener('focus',()=>{if(document.visibilityState==='visible')refreshHomeAttendance();});
if(liveSession&&liveData)render();
