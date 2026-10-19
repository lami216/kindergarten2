/* Taking attendance is an explicit, focused operation, ending in approval or discard. */
'use strict';
function rollScope(){const s=attendanceState;return s.items.filter(r=>!s.department||String(r.department_id)===s.department);}
function rollPeople(){const s=attendanceState,ids=new Set(s.rollIds||[]);return s.items.filter(r=>ids.has(r.id));}
function rollCanWrite(r){return personCan(attendanceState.resource+'.'+(r.entry?'edit':'create'));}
function rollCanClear(r){return !!r.entry&&!r.entry.cancelled_at&&personCan(attendanceState.resource+'.delete');}
function rollCounts(rows){const counts={present:0,absent:0,excused:0,unmarked:0};rows.forEach(r=>counts[selectedAttendance(r).status||'unmarked']++);return counts;}
function rollCountHTML(counts){return Object.entries({...attendanceNames,unmarked:`${I18N.tr("ui.3d9436ac9d1f")}`}).filter(([k])=>counts[k]||k==='present').map(([k,label])=>'<span class="roll-count '+k+'">'+label+' <strong>'+counts[k]+'</strong></span>').join('');}
attendanceShell=function(kind){
 const isStudent=kind==='students',title=isStudent?`${I18N.tr("ui.b305528ccd63")}`:`${I18N.tr("ui.572d73da9d87")}`,resource=isStudent?'student_attendance':'teacher_attendance';
 if(!personCan(resource+'.view'))return heading(title,`${I18N.tr("ui.76b52d65526f")}`);
 const s=attendanceState,ready=s&&s.kind===kind;
 return `${heading(title,`${I18N.tr("ui.69c4fbed91bc")}`,`<button class="secondary" data-person-nav="${isStudent?'students':'teachers'}">${I18N.tr("ui.64f129cc3498",{p0:isStudent?`${I18N.tr("ui.d776ee44ddda")}`:`${I18N.tr("ui.4be8b769b898")}`})}</button>`)}<section class="panel roll-setup"><span class="roll-step-label">${I18N.tr("ui.2ad523492c99")}</span><h2>${I18N.tr("ui.256e55276b03")}</h2><div class="person-filters body-space"><label>${I18N.tr("ui.2422f71e7f4e")}<input type="date" max="${today}" id="attendance-date" value="${esc(ready?s.date:today)}"></label><label>${I18N.tr("ui.0771c3ff9336")}<select id="attendance-department"><option value="">${I18N.tr("ui.a9ba960840d3")}</option>${personDepartments().map(d=>'<option value="'+d.id+'" '+(ready&&String(d.id)===s.department?'selected':'')+'>'+esc(d.name)+'</option>').join('')}</select></label><button type="button" class="secondary small" data-att-reload>${I18N.tr("ui.58649157ca8b")}</button></div><div id="attendance-body">${ready?attendanceBody():`<p class="tools-pending">${I18N.tr("ui.331502c62721")}</p>`}</div></section>`;
};
attendanceBody=function(){
 const s=attendanceState,rows=rollScope(),writer=rows.some(r=>rollCanWrite(r)||rollCanClear(r)),counts=rollCounts(rows),saved=rows.some(r=>!!r.entry);
 return '<div class="roll-setup-summary"><strong>'+rows.length+' '+(s.kind==='students'?`${I18N.tr("ui.9c100a9c63ac")}`:`${I18N.tr("ui.fd50da38f3d0")}`)+'</strong><div class="roll-counts">'+rollCountHTML(counts)+'</div></div>'+
  '<div class="roll-instructions"><span aria-hidden="true">🗒️</span><div><strong>'+(writer?(saved?`${I18N.tr("ui.f00310580070")}`:`${I18N.tr("ui.2543b736ebe3")}`):`${I18N.tr("ui.49943fc55ac8")}`)+'</strong><p>'+(writer?`${I18N.tr("ui.b593c8b099a9")}`:`${I18N.tr("ui.232d30a3d916")}`)+'</p></div></div><button type="button" class="primary" id="start-attendance" '+(!rows.length?'disabled':'')+'>'+(writer?(saved?`${I18N.tr("ui.8b645ac4da02")}`:`${I18N.tr("ui.3f6ec9c23b0a")}`):`${I18N.tr("ui.151bd9646f1c")}`)+'</button>';
};
function ensureRollDialog(){
 let dialog=$('#roll-dialog');if(dialog)return dialog;
 dialog=document.createElement('dialog');dialog.id='roll-dialog';dialog.className='roll-dialog';dialog.setAttribute('aria-labelledby','roll-title');document.body.append(dialog);
 dialog.oncancel=e=>{e.preventDefault();leaveAttendance(closeRoll);};
 dialog.onclick=e=>{if(e.target===dialog)leaveAttendance(closeRoll);};
 return dialog;
}
function closeRoll(){const s=attendanceState;if(s){s.rollOpen=false;s.taking=false;}const dialog=$('#roll-dialog');if(dialog?.open)dialog.close();dialog?.replaceChildren();document.body.classList.remove('taking-attendance');}
function startRoll(){
 const s=attendanceState,rows=rollScope(),writer=rows.some(r=>rollCanWrite(r)||rollCanClear(r));
 if(!rows.length||s.rollOpen)return;if(writer&&rows.length>1000){toast(`${I18N.tr("ui.8d68edafb4c3")}`,'error');return;}
 s.rollIds=rows.map(r=>r.id);s.editing=rows.some(r=>!!r.entry);s.rollOpen=true;s.taking=writer;s.rollStep='mark';s.rollQuery='';s.rollFilter='all';s.rollPage=1;s.saving=false;
 renderRoll();document.body.classList.add('taking-attendance');ensureRollDialog().showModal();$('#roll-title').focus();
}
function rollPageSize(){return I18N.lang==='fr'?(innerWidth<600?8:16):(innerWidth<600?12:innerWidth<1200?20:30);}
function rollFiltered(){
 const s=attendanceState;
 return rollPeople().filter(r=>(s.rollFilter==='unmarked'?!selectedAttendance(r).status:s.rollFilter!=='absent'||['absent','excused'].includes(selectedAttendance(r).status))&&searchText(r.name+' '+(r.identity||r.department||'')).includes(searchText(s.rollQuery)));
}
function rollPortrait(r){
 if(attendanceState.kind!=='students')return '';
 return '<span class="roll-avatar" aria-hidden="true"><span>'+esc(r.name.slice(0,1))+'</span>'+(r.photo?.data?'<img src="'+esc(r.photo.data)+'" alt="" width="32" height="32" loading="lazy" decoding="async">':'')+'</span>';
}
function rollRow(r){
 const s=attendanceState,value=selectedAttendance(r),canWrite=s.taking&&rollCanWrite(r),detail=r.identity||(s.kind==='students'?students.find(child=>child.id===r.id)?.parent:'')||r.department||'';
 return `<div class="roll-person ${value.status||'unmarked'}" data-roll-row="${esc(r.id)}"><div class="roll-person-main">${rollPortrait(r)}<div class="roll-person-name"><strong>${esc(r.name)}</strong><div class="roll-person-meta">${detail?'<small>'+esc(detail)+'</small>':''}${s.taking&&rollCanClear(r)?'<button type="button" class="roll-clear" data-roll-clear="'+esc(r.id)+'">'+(value.status?`${I18N.tr("ui.787f0c500510")}`:`${I18N.tr("ui.eec0e6368fef")}`)+'</button>':''}</div></div><div class="roll-options" role="group" aria-label="${I18N.tr("ui.5c57719fd9a6",{p0:esc(r.name)})}">${Object.entries(attendanceNames).map(([status,label])=>'<button type="button" class="roll-choice '+status+(value.status===status?' selected':'')+'" data-roll-person="'+esc(r.id)+'" data-roll-status="'+status+'" aria-pressed="'+(value.status===status)+'" '+(!canWrite?'disabled':'')+'>'+label+'</button>').join('')}</div></div>${value.status==='excused'?`<label class="roll-excuse">${I18N.tr("ui.0b8df23c54b2")}<input data-roll-excuse="${esc(r.id)}" maxlength="1000" required value="${esc(value.excuse)}" ${!canWrite?'disabled':''} placeholder="${I18N.tr("ui.283b43eebdc8")}"></label>`:''}</div>`;
}
function renderRollRows(){
 const s=attendanceState;if(!s?.rollOpen)return;
 const filtered=rollFiltered(),size=rollPageSize(),pages=Math.max(1,Math.ceil(filtered.length/size));s.rollPage=Math.min(s.rollPage,pages);
 const start=(s.rollPage-1)*size;
 $('#roll-rows').innerHTML=filtered.slice(start,start+size).map(rollRow).join('')||`<p class="empty">${I18N.tr("ui.190a3e5f712a")}</p>`;
 $('#roll-pager').innerHTML=`<button type="button" class="secondary small" data-roll-page="-1" ${s.rollPage===1?'disabled':''}>${I18N.tr("ui.a9e9d067101a")}</button><span>${I18N.tr("ui.63061e47872d",{p0:filtered.length?start+1:0,p1:Math.min(start+size,filtered.length),p2:filtered.length})}</span><button type="button" class="secondary small" data-roll-page="1" ${s.rollPage===pages?'disabled':''}>${I18N.tr("ui.5cf7af74fd3a")}</button>`;
 updateRollSummary();
}
function updateRollSummary(){
 const s=attendanceState;if(!s?.rollOpen)return;const counts=rollCounts(rollPeople());
 if($('#roll-counts'))$('#roll-counts').innerHTML=rollCountHTML(counts);
 if($('#roll-absent-count'))$('#roll-absent-count').textContent=counts.absent+counts.excused;
 if($('#roll-unmarked-count'))$('#roll-unmarked-count').textContent=counts.unmarked;
}
function renderRoll(){
 const s=attendanceState,dialog=ensureRollDialog(),rows=rollPeople(),counts=rollCounts(rows),section=personDepartments().find(d=>String(d.id)===s.department)?.name||`${I18N.tr("ui.a9ba960840d3")}`,review=s.rollStep==='review';
 dialog.innerHTML='<header class="roll-header"><div><span class="roll-step-label">'+(s.taking?(review?`${I18N.tr("ui.26431efca323")}`:s.editing?`${I18N.tr("ui.d9e1d9b36440")}`:`${I18N.tr("ui.5bb34f78340f")}`):`${I18N.tr("ui.15c0e6f59590")}`)+'</span><h2 id="roll-title" tabindex="-1">'+(review?`${I18N.tr("ui.ecf48042962b")}`:s.taking?(s.editing?`${I18N.tr("ui.7056557b6c91")}`:`${I18N.tr("ui.2b69fcf9a5d4")}`):`${I18N.tr("ui.d2082abd8c0f")}`)+'</h2><p>'+esc(section)+' · '+esc(s.date)+' · '+rows.length+' '+(s.kind==='students'?`${I18N.tr("ui.9c100a9c63ac")}`:`${I18N.tr("ui.fd50da38f3d0")}`)+'</p></div><button type="button" class="roll-exit" data-roll-exit>'+(s.taking?`${I18N.tr("ui.04b8c8d32ede")}`:`${I18N.tr("ui.ca90c297b099")}`)+' ×</button></header>'+
  '<form id="attendance-form"><div id="roll-error" class="error" role="alert"></div>'+
  (review?rollReview(rows,counts):`<div class="roll-toolbar"><label class="roll-search">${I18N.tr("ui.bc2a9f5d98c8")}<input id="roll-search" placeholder="${I18N.tr("ui.ce932f0a7d21")}" value="${esc(s.rollQuery)}"></label><div class="roll-filters"><button type="button" data-roll-filter="all" aria-pressed="${s.rollFilter==='all'}">${I18N.tr("ui.bcda95d71da1",{p0:rows.length})}</button><button type="button" data-roll-filter="absent" aria-pressed="${s.rollFilter==='absent'}">${I18N.tr("ui.84ee783608e3")} <span id="roll-absent-count">${counts.absent+counts.excused}</span></button><button type="button" data-roll-filter="unmarked" aria-pressed="${s.rollFilter==='unmarked'}">${I18N.tr("ui.3d9436ac9d1f")} <span id="roll-unmarked-count">${counts.unmarked}</span></button></div></div><div class="roll-session-note">${s.taking?`${I18N.tr("ui.59dd497eee3b")}`:`${I18N.tr("ui.9dc4221fabb4")}`}</div><div id="roll-counts" class="roll-counts">${rollCountHTML(counts)}</div><div id="roll-scroll" class="roll-scroll"><div id="roll-rows" class="roll-rows"></div></div><div id="roll-pager" class="roll-pager"></div>`)+
  '<footer class="roll-footer"><div><strong>'+(s.taking?`${I18N.tr("ui.beb372accb21")}`:`${I18N.tr("ui.63ee1c9daa30")}`)+'</strong><small>'+(s.taking?`${I18N.tr("ui.03b66c3b47dc")}`:`${I18N.tr("ui.a4cf3ea4c52b")}`)+'</small></div><div class="actions">'+(review?`<button type="button" class="secondary" data-roll-back>${I18N.tr("ui.6b32e9e53dd6")}</button>`:'')+(s.taking?(review?`<button class="primary" id="roll-save" type="submit">${I18N.tr("ui.f2af12bae8a8")}</button>`:`<button class="primary" id="roll-review" type="button" data-roll-review>${I18N.tr("ui.ccd85a2b3578")}</button>`):`<button type="button" class="secondary" data-roll-exit>${I18N.tr("ui.087ca9ec0a08")}</button>`)+'</div></footer></form>';
 if(!review){renderRollRows();$('#roll-search').oninput=e=>{s.rollQuery=e.target.value;s.rollPage=1;renderRollRows();};}
}
function rollReview(rows,counts){
 const absent=rows.filter(r=>['absent','excused'].includes(selectedAttendance(r).status)),cleared=rows.filter(r=>attendanceState.drafts.has(r.id)&&!selectedAttendance(r).status);
 return `<section class="roll-review-screen"><div class="roll-review-icon" aria-hidden="true">✓</div><h3>${I18N.tr("ui.36d8f467cd28")}</h3><p>${I18N.tr("ui.fdf9f6181874",{p0:rows.length})}</p><div class="roll-counts roll-review-counts">${rollCountHTML(counts)}</div><div class="roll-review-absent">${absent.length?`<h4>${I18N.tr("ui.84ee783608e3")}</h4>${absent.map(r=>'<div><strong>'+esc(r.name)+'</strong><span>'+attendanceNames[selectedAttendance(r).status]+'</span>'+(selectedAttendance(r).excuse?'<small>'+esc(selectedAttendance(r).excuse)+'</small>':'')+'</div>').join('')}`:counts.unmarked?`<p>${I18N.tr("ui.52dfc4a5bfc5")}</p>`:`<p>${I18N.tr("ui.9b8585e61219")}</p>`}</div>${cleared.length?`<div class="roll-review-absent"><h4>${I18N.tr("ui.b3be89b31f9a",{p0:cleared.length})}</h4><p class="muted">${I18N.tr("ui.5a3739880ff4")}</p>${cleared.map(r=>`<div><strong>${esc(r.name)}</strong><span>${I18N.tr("ui.43b81c909fb3")}</span></div>`).join('')}</div>`:''}</section>`;
}
function validateRoll(){
 const s=attendanceState,rows=rollPeople(),excuse=rows.find(r=>selectedAttendance(r).status==='excused'&&!selectedAttendance(r).excuse.trim()),missing=rows.find(r=>!selectedAttendance(r).status&&rollCanWrite(r)&&!r.entry?.cancelled_at&&!s.drafts.has(r.id)),invalid=excuse||missing;
 if(!invalid)return true;
 s.rollStep='mark';s.rollQuery='';s.rollFilter=excuse?'absent':'unmarked';s.rollPage=Math.floor(rollFiltered().findIndex(r=>r.id===invalid.id)/rollPageSize())+1;renderRoll();
 $('#roll-error').textContent=excuse?`${I18N.tr("ui.a50ec39c99e5",{p0:invalid.name})}`:`${I18N.tr("ui.e15feb6fcaa2",{p0:invalid.name})}`;
 document.querySelector(excuse?'[data-roll-excuse="'+CSS.escape(invalid.id)+'"]':'[data-roll-person="'+CSS.escape(invalid.id)+'"]')?.focus();
 return false;
}
repaintAttendance=function(){if(attendanceState?.rollOpen){renderRollRows();return;}if($('#attendance-body'))$('#attendance-body').innerHTML=attendanceBody();};
leaveAttendance=function(action){
 const s=attendanceState;if(s?.saving){toast(`${I18N.tr("ui.01b480a493c0")}`);return;}
 if(!s?.taking&&!s?.drafts.size){closeRoll();action();return;}
 openProtected(`${I18N.tr("ui.38ba64a8a786")}`,`<p>${I18N.tr("ui.3a6cd9ea79bf")}</p><div class="actions body-space"><button class="primary" id="keep-attendance">${I18N.tr("ui.1b390722be82")}</button><button class="secondary danger" id="discard-attendance">${I18N.tr("ui.011bfa9fcb43")}</button></div>`);
 $('#keep-attendance').onclick=()=>$('#record-dialog').close();$('#discard-attendance').onclick=()=>{s.drafts.clear();s.taking=false;$('#record-dialog').close();closeRoll();action();if(page.endsWith('-attendance'))repaintAttendance();};
};
const rollSubmit=liveSubmit;
liveSubmit=async function(form){
 if(form.id!=='attendance-form')return rollSubmit(form);
 const s=attendanceState;if(!s?.taking||s.saving||s.rollStep!=='review'||!validateRoll())return;
 s.saving=true;const controls=[...ensureRollDialog().querySelectorAll('input,button')].map(el=>[el,el.disabled]);controls.forEach(([el])=>el.disabled=true);$('#roll-save').textContent=`${I18N.tr("ui.2eb1f391295a")}`;
 try{
  if(s.drafts.size)await liveCall('attendance.save',{kind:s.kind,date:s.date,entries:[...s.drafts.values()],reason:`${I18N.tr("ui.9f470c60f5aa")}`});
 }catch(e){s.saving=false;controls.forEach(([el,disabled])=>el.disabled=disabled);$('#roll-save').textContent=`${I18N.tr("ui.f2af12bae8a8")}`;throw e;}
 const scopeCount=s.rollIds.length;s.drafts.clear();s.taking=false;s.saving=false;closeRoll();
 try{await liveLoad();await loadAttendance(s.kind,s.date);toast(`${I18N.tr("ui.cd1f0b74c80e",{p0:scopeCount,p1:s.kind==='students'?`${I18N.tr("ui.9c100a9c63ac")}`:`${I18N.tr("ui.fd50da38f3d0")}`})}`);}
 catch(e){toast(`${I18N.tr("ui.1e74bf7fb465")}`,'error');}
 pageTop();
};
document.addEventListener('input',e=>{const id=e.target.dataset.rollExcuse;if(id&&attendanceState?.rollOpen&&!attendanceState.saving){putAttendance(id,'excused',e.target.value);updateRollSummary();}},true);
document.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;const handle=()=>{e.preventDefault();e.stopImmediatePropagation();};
 if(b.id==='start-attendance'){handle();startRoll();return;}
 if(b.hasAttribute('data-roll-exit')){handle();leaveAttendance(closeRoll);return;}
 if(!attendanceState?.rollOpen||attendanceState.saving)return;
 const s=attendanceState;
 if(b.dataset.rollClear){handle();const r=s.items.find(r=>r.id===b.dataset.rollClear);if(!s.taking||!rollCanClear(r))return;const value=selectedAttendance(r);putAttendance(r.id,value.status?'':r.entry.status,value.status?'':r.entry.excuse);renderRollRows();return;}
 if(b.dataset.rollPerson){
  handle();const r=s.items.find(r=>r.id===b.dataset.rollPerson),status=b.dataset.rollStatus;
  if(!r||!s.taking||!rollCanWrite(r)||!Object.hasOwn(attendanceNames,status))return;
  putAttendance(r.id,status);const scroll=$('#roll-scroll'),top=scroll.scrollTop;renderRollRows();scroll.scrollTop=top;
  document.querySelector(status==='excused'?'[data-roll-excuse="'+CSS.escape(r.id)+'"]':'[data-roll-person="'+CSS.escape(r.id)+'"][data-roll-status="'+status+'"]')?.focus({preventScroll:status!=='excused'});return;
 }
 if(b.dataset.rollFilter){handle();s.rollFilter=b.dataset.rollFilter;s.rollPage=1;renderRoll();return;}
 if(b.dataset.rollPage){handle();s.rollPage+=Number(b.dataset.rollPage);renderRollRows();$('#roll-scroll').scrollTop=0;return;}
 if(b.hasAttribute('data-roll-review')){handle();if(validateRoll()){s.rollStep='review';renderRoll();}return;}
 if(b.hasAttribute('data-roll-back')){handle();s.rollStep='mark';renderRoll();}
},true);
window.addEventListener('beforeunload',e=>{if(attendanceState?.taking){e.preventDefault();e.returnValue='';}});
const rollLogin=liveLoginScreen;
liveLoginScreen=function(){if(attendanceState){attendanceState.drafts.clear();attendanceState.taking=false;}closeRoll();rollLogin();};

let rollResize;window.addEventListener('resize',()=>{clearTimeout(rollResize);rollResize=setTimeout(()=>{if(attendanceState?.rollOpen&&attendanceState.rollStep==='mark')renderRollRows();},150);});
if(liveSession&&liveData&&page.endsWith('-attendance'))render();

document.addEventListener('error',e=>{if(e.target.matches?.('.roll-avatar img'))e.target.remove();},true);
