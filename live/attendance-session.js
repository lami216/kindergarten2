/* Taking attendance is an explicit, focused operation, ending in approval or discard. */
'use strict';
function rollScope(){const s=attendanceState;return s.items.filter(r=>!s.department||String(r.department_id)===s.department);}
function rollPeople(){const s=attendanceState,ids=new Set(s.rollIds||[]);return s.items.filter(r=>ids.has(r.id));}
function rollCanWrite(r){return personCan(attendanceState.resource+'.'+(r.entry?'edit':'create'));}
function rollCanClear(r){return !!r.entry&&!r.entry.cancelled_at&&personCan(attendanceState.resource+'.delete');}
function rollCounts(rows){const counts={present:0,absent:0,excused:0,unmarked:0};rows.forEach(r=>counts[selectedAttendance(r).status||'unmarked']++);return counts;}
function rollCountHTML(counts){return Object.entries({...attendanceNames,unmarked:'لم يسجل'}).filter(([k])=>counts[k]||k==='present').map(([k,label])=>'<span class="roll-count '+k+'">'+label+' <strong>'+counts[k]+'</strong></span>').join('');}
attendanceShell=function(kind){
 const isStudent=kind==='students',title=isStudent?'حضور الطلاب':'حضور المعلمين',resource=isStudent?'student_attendance':'teacher_attendance';
 if(!personCan(resource+'.view'))return heading(title,'ليست لديك صلاحية لعرض هذا السجل.');
 const s=attendanceState,ready=s&&s.kind===kind;
 return heading(title,'اختر اليوم والقسم لتسجيل الحضور أو تعديل كشف مسجل.','<button class="secondary" data-person-nav="'+(isStudent?'students':'teachers')+'">العودة إلى '+(isStudent?'الطلاب':'المعلمين')+'</button>')+
  '<section class="panel roll-setup"><span class="roll-step-label">١ · تجهيز الكشف</span><h2>كشف الحضور اليومي</h2><div class="person-filters body-space"><label>اليوم<input type="date" max="'+today+'" id="attendance-date" value="'+esc(ready?s.date:today)+'"></label><label>القسم<select id="attendance-department"><option value="">كل الأقسام</option>'+personDepartments().map(d=>'<option value="'+d.id+'" '+(ready&&String(d.id)===s.department?'selected':'')+'>'+esc(d.name)+'</option>').join('')+'</select></label><button type="button" class="secondary small" data-att-reload>تحديث اليوم</button></div><div id="attendance-body">'+(ready?attendanceBody():'<p class="tools-pending">جارٍ تجهيز الكشف…</p>')+'</div>'+'</section>';
};
attendanceBody=function(){
 const s=attendanceState,rows=rollScope(),writer=rows.some(r=>rollCanWrite(r)||rollCanClear(r)),counts=rollCounts(rows),saved=rows.some(r=>!!r.entry);
 return '<div class="roll-setup-summary"><strong>'+rows.length+' '+(s.kind==='students'?'طالبًا':'معلمًا')+'</strong><div class="roll-counts">'+rollCountHTML(counts)+'</div></div>'+
  '<div class="roll-instructions"><span aria-hidden="true">🗒️</span><div><strong>'+(writer?(saved?'تعديل الحضور المسجل':'اختر حالة كل اسم'):'عرض الكشف المسجل')+'</strong><p>'+(writer?'اختر حاضر، غائب أو غائب بعذر لكل اسم. لا تُحدّد أي حالة تلقائيًا، ولا تُحفظ التغييرات حتى مراجعة الكشف واعتماده.':'يمكنك الاطلاع على الحالات المسجلة دون تعديلها.')+'</p></div></div><button type="button" class="primary" id="start-attendance" '+(!rows.length?'disabled':'')+'>'+(writer?(saved?'تعديل الحضور ←':'بدء أخذ الحضور ←'):'عرض الكشف ←')+'</button>';
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
 if(!rows.length||s.rollOpen)return;if(writer&&rows.length>1000){toast('اختر قسمًا لتقسيم الكشف إلى مجموعات أصغر.','error');return;}
 s.rollIds=rows.map(r=>r.id);s.editing=rows.some(r=>!!r.entry);s.rollOpen=true;s.taking=writer;s.rollStep='mark';s.rollQuery='';s.rollFilter='all';s.rollPage=1;s.saving=false;
 renderRoll();document.body.classList.add('taking-attendance');ensureRollDialog().showModal();$('#roll-title').focus();
}
function rollPageSize(){return innerWidth<600?12:innerWidth<1200?20:30;}
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
 return '<div class="roll-person '+(value.status||'unmarked')+'" data-roll-row="'+esc(r.id)+'"><div class="roll-person-main">'+rollPortrait(r)+'<div class="roll-person-name"><strong>'+esc(r.name)+'</strong><div class="roll-person-meta">'+(detail?'<small>'+esc(detail)+'</small>':'')+(s.taking&&rollCanClear(r)?'<button type="button" class="roll-clear" data-roll-clear="'+esc(r.id)+'">'+(value.status?'إلغاء اليوم':'تراجع')+'</button>':'')+'</div></div><div class="roll-options" role="group" aria-label="حضور '+esc(r.name)+'">'+Object.entries(attendanceNames).map(([status,label])=>'<button type="button" class="roll-choice '+status+(value.status===status?' selected':'')+'" data-roll-person="'+esc(r.id)+'" data-roll-status="'+status+'" aria-pressed="'+(value.status===status)+'" '+(!canWrite?'disabled':'')+'>'+label+'</button>').join('')+'</div></div>'+
  (value.status==='excused'?'<label class="roll-excuse">العذر *<input data-roll-excuse="'+esc(r.id)+'" maxlength="1000" required value="'+esc(value.excuse)+'" '+(!canWrite?'disabled':'')+' placeholder="سبب الغياب"></label>':'')+'</div>';
}
function renderRollRows(){
 const s=attendanceState;if(!s?.rollOpen)return;
 const filtered=rollFiltered(),size=rollPageSize(),pages=Math.max(1,Math.ceil(filtered.length/size));s.rollPage=Math.min(s.rollPage,pages);
 const start=(s.rollPage-1)*size;
 $('#roll-rows').innerHTML=filtered.slice(start,start+size).map(rollRow).join('')||'<p class="empty">لا توجد أسماء مطابقة.</p>';
 $('#roll-pager').innerHTML='<button type="button" class="secondary small" data-roll-page="-1" '+(s.rollPage===1?'disabled':'')+'>السابق</button><span>'+(filtered.length?start+1:0)+'–'+Math.min(start+size,filtered.length)+' من '+filtered.length+'</span><button type="button" class="secondary small" data-roll-page="1" '+(s.rollPage===pages?'disabled':'')+'>التالي</button>';
 updateRollSummary();
}
function updateRollSummary(){
 const s=attendanceState;if(!s?.rollOpen)return;const counts=rollCounts(rollPeople());
 if($('#roll-counts'))$('#roll-counts').innerHTML=rollCountHTML(counts);
 if($('#roll-absent-count'))$('#roll-absent-count').textContent=counts.absent+counts.excused;
 if($('#roll-unmarked-count'))$('#roll-unmarked-count').textContent=counts.unmarked;
}
function renderRoll(){
 const s=attendanceState,dialog=ensureRollDialog(),rows=rollPeople(),counts=rollCounts(rows),section=personDepartments().find(d=>String(d.id)===s.department)?.name||'كل الأقسام',review=s.rollStep==='review';
 dialog.innerHTML='<header class="roll-header"><div><span class="roll-step-label">'+(s.taking?(review?'٣ · اعتماد الكشف':s.editing?'٢ · تعديل الحضور':'٢ · أخذ الحضور'):'عرض الكشف')+'</span><h2 id="roll-title" tabindex="-1">'+(review?'مراجعة الحضور':s.taking?(s.editing?'تعديل الحضور':'تسجيل الحضور'):'كشف الحضور')+'</h2><p>'+esc(section)+' · '+esc(s.date)+' · '+rows.length+' '+(s.kind==='students'?'طالبًا':'معلمًا')+'</p></div><button type="button" class="roll-exit" data-roll-exit>'+(s.taking?'إلغاء الجلسة':'إغلاق')+' ×</button></header>'+
  '<form id="attendance-form"><div id="roll-error" class="error" role="alert"></div>'+
  (review?rollReview(rows,counts):'<div class="roll-toolbar"><label class="roll-search">بحث عن اسم<input id="roll-search" placeholder="ابحث بسرعة…" value="'+esc(s.rollQuery)+'"></label><div class="roll-filters"><button type="button" data-roll-filter="all" aria-pressed="'+(s.rollFilter==='all')+'">الكل '+rows.length+'</button><button type="button" data-roll-filter="absent" aria-pressed="'+(s.rollFilter==='absent')+'">الغائبون <span id="roll-absent-count">'+(counts.absent+counts.excused)+'</span></button><button type="button" data-roll-filter="unmarked" aria-pressed="'+(s.rollFilter==='unmarked')+'">لم يسجل <span id="roll-unmarked-count">'+counts.unmarked+'</span></button></div></div><div class="roll-session-note">'+(s.taking?'اختر حالة كل اسم بنفسك. الغياب بعذر يحتاج كتابة السبب.':'هذه الحالات المسجلة؛ لا توجد صلاحية لتغييرها.')+'</div><div id="roll-counts" class="roll-counts">'+rollCountHTML(counts)+'</div><div id="roll-scroll" class="roll-scroll"><div id="roll-rows" class="roll-rows"></div></div><div id="roll-pager" class="roll-pager"></div>')+
  '<footer class="roll-footer"><div><strong>'+(s.taking?'لم يُعتمد الكشف بعد':'عرض فقط')+'</strong><small>'+(s.taking?'لن تُحفظ الحالات حتى الاعتماد.':'الحالات غير المسجلة لا تدخل في النسب.')+'</small></div><div class="actions">'+(review?'<button type="button" class="secondary" data-roll-back>العودة للأسماء</button>':'')+(s.taking?(review?'<button class="primary" id="roll-save" type="submit">اعتماد وحفظ الكشف ✓</button>':'<button class="primary" id="roll-review" type="button" data-roll-review>مراجعة الكشف ←</button>'):'<button type="button" class="secondary" data-roll-exit>إغلاق الكشف</button>')+'</div></footer></form>';
 if(!review){renderRollRows();$('#roll-search').oninput=e=>{s.rollQuery=e.target.value;s.rollPage=1;renderRollRows();};}
}
function rollReview(rows,counts){
 const absent=rows.filter(r=>['absent','excused'].includes(selectedAttendance(r).status)),cleared=rows.filter(r=>attendanceState.drafts.has(r.id)&&!selectedAttendance(r).status);
 return '<section class="roll-review-screen"><div class="roll-review-icon" aria-hidden="true">✓</div><h3>الكشف جاهز للاعتماد</h3><p>'+rows.length+' اسمًا · راجع الملخص ثم احفظ الكشف.</p><div class="roll-counts roll-review-counts">'+rollCountHTML(counts)+'</div><div class="roll-review-absent">'+(absent.length?'<h4>الغائبون</h4>'+absent.map(r=>'<div><strong>'+esc(r.name)+'</strong><span>'+attendanceNames[selectedAttendance(r).status]+'</span>'+(selectedAttendance(r).excuse?'<small>'+esc(selectedAttendance(r).excuse)+'</small>':'')+'</div>').join(''):(counts.unmarked?'<p>لا يوجد غياب ضمن الأسماء المسجلة.</p>':'<p>الجميع حاضر في هذا الكشف.</p>'))+'</div>'+(cleared.length?'<div class="roll-review-absent"><h4>إلغاء تسجيل اليوم ('+cleared.length+')</h4><p class="muted">ستُزال هذه الحالات من نسب الحضور، ويُحفظ الإلغاء في سجل التغييرات.</p>'+cleared.map(r=>'<div><strong>'+esc(r.name)+'</strong><span>إلغاء التسجيل</span></div>').join('')+'</div>':'')+'</section>';
}
function validateRoll(){
 const s=attendanceState,rows=rollPeople(),excuse=rows.find(r=>selectedAttendance(r).status==='excused'&&!selectedAttendance(r).excuse.trim()),missing=rows.find(r=>!selectedAttendance(r).status&&rollCanWrite(r)&&!r.entry?.cancelled_at&&!s.drafts.has(r.id)),invalid=excuse||missing;
 if(!invalid)return true;
 s.rollStep='mark';s.rollQuery='';s.rollFilter=excuse?'absent':'unmarked';s.rollPage=Math.floor(rollFiltered().findIndex(r=>r.id===invalid.id)/rollPageSize())+1;renderRoll();
 $('#roll-error').textContent=excuse?'اكتب عذر الغياب لـ '+invalid.name+' قبل مراجعة الكشف.':'اختر حالة الحضور لـ '+invalid.name+'؛ لا تُسجل الحالات تلقائيًا.';
 document.querySelector(excuse?'[data-roll-excuse="'+CSS.escape(invalid.id)+'"]':'[data-roll-person="'+CSS.escape(invalid.id)+'"]')?.focus();
 return false;
}
repaintAttendance=function(){if(attendanceState?.rollOpen){renderRollRows();return;}if($('#attendance-body'))$('#attendance-body').innerHTML=attendanceBody();};
leaveAttendance=function(action){
 const s=attendanceState;if(s?.saving){toast('جارٍ اعتماد الكشف؛ انتظر اكتمال الحفظ.');return;}
 if(!s?.taking&&!s?.drafts.size){closeRoll();action();return;}
 openProtected('جلسة الحضور لم تُعتمد','<p>أنت الآن تأخذ الحضور. ارجع لإكمال الكشف وحفظه، أو ألغِ الجلسة صراحةً دون حفظ.</p><div class="actions body-space"><button class="primary" id="keep-attendance">إكمال أخذ الحضور</button><button class="secondary danger" id="discard-attendance">إلغاء الجلسة دون حفظ</button></div>');
 $('#keep-attendance').onclick=()=>$('#record-dialog').close();$('#discard-attendance').onclick=()=>{s.drafts.clear();s.taking=false;$('#record-dialog').close();closeRoll();action();if(page.endsWith('-attendance'))repaintAttendance();};
};
const rollSubmit=liveSubmit;
liveSubmit=async function(form){
 if(form.id!=='attendance-form')return rollSubmit(form);
 const s=attendanceState;if(!s?.taking||s.saving||s.rollStep!=='review'||!validateRoll())return;
 s.saving=true;const controls=[...ensureRollDialog().querySelectorAll('input,button')].map(el=>[el,el.disabled]);controls.forEach(([el])=>el.disabled=true);$('#roll-save').textContent='جارٍ اعتماد الكشف…';
 try{
  if(s.drafts.size)await liveCall('attendance.save',{kind:s.kind,date:s.date,entries:[...s.drafts.values()],reason:'اعتماد كشف الحضور اليومي'});
 }catch(e){s.saving=false;controls.forEach(([el,disabled])=>el.disabled=disabled);$('#roll-save').textContent='اعتماد وحفظ الكشف ✓';throw e;}
 const scopeCount=s.rollIds.length;s.drafts.clear();s.taking=false;s.saving=false;closeRoll();
 try{await liveLoad();await loadAttendance(s.kind,s.date);toast('تم اعتماد وحفظ كشف '+scopeCount+' '+(s.kind==='students'?'طالبًا':'معلمًا')+'.');}
 catch(e){toast('تم اعتماد الكشف، لكن تعذّر تحديث عرضه. حدّث الصفحة قبل تسجيل كشف آخر.','error');}
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
