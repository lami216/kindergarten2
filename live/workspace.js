/* A single live workspace. All writes still go through the authorized bridge. */
'use strict';
let receiptPageId=null,toolTab='fees',toolTable='parents',toolRows=null,toolQuery='',toolPage=1,toolArchived=false;
let feeDraft=null,teacherOptions=[],reportData=null,reportRequest=null,reportExport=null;
const listState=new Map();let noticeTimer;
const workspaceCall=liveCall;
liveCall=async function(operation,data){
    const identity=liveSession,result=await workspaceCall(operation,data);
    if(identity&&identity!==liveSession&&!['login','session'].includes(operation))throw Error('تغيّرت جلسة الدخول؛ أعد فتح الصفحة.');
    return result;
};
const workspaceLoginScreen=liveLoginScreen;
liveLoginScreen=function(){
    toolFetch++;toolRows=null;feeDraft=null;teacherOptions=[];reportData=null;reportRequest=null;
    receiptPageId=null;includeArchivedReceipts=false;listState.clear();$('#nav-workspace')?.remove();
    workspaceLoginScreen();
};
function pageTop(){window.scrollTo({top:0,left:0,behavior:'instant'});document.querySelector('main')?.scrollTo(0,0);}
toast=function(message,kind='success'){
    const box=$('#toast');clearTimeout(noticeTimer);box.dataset.kind=kind;box.setAttribute('role',kind==='error'?'alert':'status');
    box.setAttribute('aria-live',kind==='error'?'assertive':'polite');box.textContent=message;box.classList.add('show');
    noticeTimer=setTimeout(()=>box.classList.remove('show'),6500);
};
const workspaceNavigate=navigate;
navigate=function(next){receiptPageId=null;workspaceNavigate(next);pageTop();};
const workspaceSaved=liveSaved;
liveSaved=async function(operation,data,form){
    const result=await workspaceSaved(operation,data,form);
    if(operation==='students.restore'){profileId=data.student;page='students';render();}
    if(operation==='records.change'&&data.type==='receipts'){
        receiptPageId=data.mode==='edit'?result.id:data.id;page='receipt';render();
    }
    pageTop();return result;
};
function pageSlice(kind,rows,renderer){
    let state=listState.get(kind),signature=rows.map(r=>r.id??r.key).join('|');
    if(!state||state.signature!==signature)state={page:1,signature};
    state.rows=rows;state.renderer=renderer;state.pages=Math.max(1,Math.ceil(rows.length/15));state.page=Math.min(state.page,state.pages);
    listState.set(kind,state);return renderer(rows.slice((state.page-1)*15,state.page*15));
}
function pager(kind){const s=listState.get(kind);return !s?'' : '<div class="pager"><button type="button" class="secondary" data-list="'+kind+'" data-delta="-1" '+(s.page===1?'disabled':'')+'>السابق</button><span>'+s.page+' / '+s.pages+' · '+s.rows.length+' سجل</span><button type="button" class="secondary" data-list="'+kind+'" data-delta="1" '+(s.page===s.pages?'disabled':'')+'>التالي</button></div>';}
const workspaceStudentRows=studentRows;
studentRows=rows=>pageSlice('students',rows,workspaceStudentRows)+'<tr><td colspan="4">'+pager('students')+'</td></tr>';
let includeArchivedReceipts=false;
receiptRows=function(){
    const rows=receipts.filter(r=>{
        const s=students.find(s=>s.id===r.student);
        return s&&(!s.cancelled||includeArchivedReceipts||receiptChild===s.id)&&(!receiptChild||r.student===receiptChild)&&
            (childMatches(s,receiptSearch)||String(r.id).includes(searchText(receiptSearch)));
    }).slice().reverse();
    const html=pageSlice('receipts',rows,rs=>rs.map(r=>{
        const s=students.find(s=>s.id===r.student);
        return '<div class="list-card" data-receipt-row="'+r.id+'"><div><strong>'+esc(s.name)+'</strong><small>وصل '+r.id+' · '+esc(r.date)+(s.cancelled?' · ملف مؤرشف':'')+'</small></div><div class="actions"><span class="status '+(r.cancelled?'amber':'')+'">'+money(r.amount)+' أوقية'+(r.cancelled?' · ملغى / مصحح':'')+'</span><button class="secondary small" data-receipt="'+r.id+'">فتح الوصل ←</button></div></div>';
    }).join('')||'<div class="empty">لا توجد وصولات مطابقة.</div>');
    return html+pager('receipts');
};
paymentOptions=function(term=''){return '<option value="">اختر طفلًا…</option>'+students.filter(s=>!s.cancelled&&childMatches(s,term)).map(s=>'<option value="'+esc(s.id)+'">'+esc([s.name,s.parent,s.phone].filter(Boolean).join(' · '))+'</option>').join('');};
const workspaceReceiptList=receiptList;
receiptList=()=>workspaceReceiptList().replace('</label>','</label><label class="check-row body-space"><input type="checkbox" id="receipt-archived" '+(includeArchivedReceipts?'checked':'')+'>إظهار وصولات الملفات المؤرشفة</label>');
openReceipt=function(id){receiptPageId=Number(id);page='receipt';render();pageTop();};
function receiptScreen(){
    const r=receipts.find(r=>r.id===receiptPageId),s=r&&students.find(s=>s.id===r.student);
    if(!r||!s)return heading('الوصل','لم يعد متاحًا لهذا الحساب.','<button class="secondary" data-return-receipts>العودة للوصولات</button>');
    return heading('وصل قبض #'+r.id,'مستند مستقل، وتفاصيله وإجراءاته في مكان واحد.','<button class="secondary" data-return-receipts>العودة للوصولات</button>')+
        '<section class="panel page-receipt" id="receipt-page"><span class="badge">روضة أطفال فودي حبيب ساكرا</span>'+
        (r.cancelled?'<p class="notice-box">ملغى / مصحح — محفوظ للمراجعة ولا يدخل في المقبوضات.</p>':'')+
        '<h2 class="body-space">'+esc(s.name)+'</h2><p class="muted">'+esc(s.parent)+' · '+esc(s.phone)+'</p><p>تاريخ القبض: '+esc(r.date)+'</p>'+
        '<div class="receipt-total">'+money(r.amount)+' <small>أوقية قديمة</small></div><div class="summary-detail">'+
        detailLine('التسجيل',r.registration)+detailLine('الجيليه',r.gilet)+detailLine('الشهرية',r.monthly)+'</div>'+
        '<div class="actions"><a class="secondary" href="/api/receipt/'+r.id+'" target="_blank" rel="noopener">تنزيل PDF</a>'+recordActions('receipts',r.id,r.cancelled)+'</div></section>';
}
let expenseTerm='';
const workspaceExpensePage=expensePage;
expensePage=function(){
    const t=document.createElement('template');t.innerHTML=workspaceExpensePage();
    [...t.content.querySelectorAll('h2')].find(h=>h.textContent.includes('تعديل أو إلغاء مصروف'))?.closest('.panel')?.remove();
    const table=t.content.querySelector('table');
    if(table){
        table.querySelector('thead tr').insertAdjacentHTML('beforeend','<th>الإجراء</th>');
        const rows=expenses.filter(e=>!e.cancelled&&searchText(e.category+' '+e.payee).includes(searchText(expenseTerm))).slice().reverse();
        const html=pageSlice('expenses',rows,rs=>rs.map(e=>'<tr><td>'+esc(e.category)+'<small>'+esc(e.payee)+'</small></td><td>'+money(e.amount)+'</td><td>'+money(e.paid)+'</td><td>'+money(e.amount-e.paid)+'</td><td>'+recordActions('expenses',e.id)+(e.amount>e.paid&&demoCan('expenses','edit')?'<button class="secondary small" data-settle="'+e.id+'">تسديد المتبقي</button>':'')+'</td></tr>').join(''));
        table.querySelector('tbody').innerHTML=html+'<tr><td colspan="5">'+pager('expenses')+'</td></tr>';
        table.closest('.table-wrap').insertAdjacentHTML('beforebegin','<label class="body-space">بحث في المصروفات<input id="expense-search" value="'+esc(expenseTerm)+'" placeholder="اسم المصروف أو المستلم"></label>');
    }
    return t.innerHTML;
};
function detailLine(label,value){return '<div class="summary-line"><span>'+esc(label)+'</span><strong>'+esc(typeof value==='number'?money(value):value)+'</strong></div>';}
demoGrantFields=function(prefix,permissions=[]){
    return Object.entries(liveData.resources).map(([area,resource])=>'<fieldset class="grant-row"><legend>'+esc(resource.title)+'</legend>'+resource.actions.map(action=>{
        const value=uiPermission(area+'.'+action),label=demoActions[action==='delete'?'cancel':action];
        return '<label class="check-row"><input type="checkbox" name="grant" value="'+value+'" '+(permissions.includes(value)?'checked':'')+'>'+label+'</label>';
    }).join('')+'</fieldset>').join('');
};
liveGrants=function(values){return [...new Set(values.map(livePermission))];};
demoShowMetrics=function(){
    const user=demoUsers.find(u=>u.id===$('#demo-activity-user').value),m=demoMetrics(user);
    const labels=user.permissions.map(p=>{const server=livePermission(p),[area,action]=server.split('.');return (liveData.resources[area]?.title||area)+': '+(demoActions[action==='delete'?'cancel':action]||action);});
    $('#demo-activity-body').innerHTML='<p class="muted">'+esc(user.admin?'مدير بجميع الصلاحيات':labels.join('، ')||'بلا صلاحيات')+'</p><div class="stats">'+stat('🎒','طلاب سجلهم',m.students)+stat('📦','مصروفات سجلها',m.expenses)+stat('💵','صافي مصروفاته',money(m.cash),'أوقية قديمة')+stat('🧾','دفعات سجلها',m.payments)+stat('✏️','تعديلات محفوظة',m.edits)+stat('🕘','إلغاءات محفوظة',m.cancellations)+'</div>';
};
function archiveScreen(){
    const input=archiveScreen.query||'',rows=students.filter(s=>s.cancelled&&childMatches(s,input));
    const html=pageSlice('archives',rows,rs=>rs.map(s=>'<div class="list-card"><div><strong>'+esc(s.name)+'</strong><small>'+esc(s.parent)+' · '+esc(s.phone)+'</small></div><div class="actions"><button class="secondary small" data-archive-profile="'+esc(s.id)+'">مراجعة الملف</button>'+(canRestore()?'<button class="secondary small" data-restore="'+esc(s.id)+'">استرجاع</button>':'')+'</div></div>').join('')||'<div class="empty">لا توجد ملفات مؤرشفة مطابقة.</div>');
    return heading('الطلاب المؤرشفون','ملفات منفصلة عن الطلاب الحاليين. الاسترجاع لا يحتسب أشهر الغياب.','<button class="secondary" data-back-active>الطلاب الحاليون</button>')+
        '<div class="panel"><label>بحث في الأرشيف<input id="archive-search" value="'+esc(input)+'" placeholder="الاسم أو هاتف أحد الوالدين"></label><div id="archive-rows">'+html+pager('archives')+'</div></div>';
}
function openProtected(title,body){
    $('#record-content').innerHTML='<div class="dialog-head"><h2>'+esc(title)+'</h2><button type="button" class="quiet" id="workspace-close" aria-label="إغلاق">✕</button></div>'+body;
    const d=$('#record-dialog');d.showModal();protectEditWindow(d,['workspace-close']);
}
function confirmation(){return '<label class="body-space">السبب *<input name="reason" required maxlength="2000"></label><label class="check-row"><input type="checkbox" name="confirmed" required>أؤكد الإجراء بعد المراجعة</label><p class="error" role="alert"></p><button class="primary body-space">تأكيد وحفظ</button>';}
function canRestore(){return demoCan('students','edit')&&(demoActor.admin||liveSession.user.permissions.includes('accounts.edit'));}
function restoreWindow(id){
    const s=students.find(s=>s.id===id);
    openProtected('استرجاع '+s.name,'<form id="restore-form" data-student="'+esc(id)+'"><p class="archive-note">يعود الملف للمراجعة دون فرض رسوم عن فترة الغياب. يمكنك إسقاط الدين من ملفه، ثم أرشفته مجددًا.</p>'+confirmation()+'</form>');
    $('#restore-form').dataset.revision=s.revision;$('#restore-form').dataset.accountRevision=s.account_revision||'';
}
function waiverWindow(id){
    const s=students.find(s=>s.id===id);
    if(!s.account?.due){toast('لا يوجد دين مستحق لإسقاطه.');return;}
    openProtected('إسقاط دين '+s.name,'<form id="waiver-form" data-student="'+esc(id)+'"><p>المبلغ المستحق: <strong>'+money(s.account.due)+' أوقية قديمة</strong></p><p class="archive-note">إسقاط الدين ليس دفعة ولا يضيف نقدًا. تبقى الرسوم والوصولات السابقة وسجل الإجراء محفوظة.</p>'+confirmation()+'</form>');
    Object.assign($('#waiver-form').dataset,{due:String(s.account.due),revision:String(s.ledger_revision)});
}
const workspaceProfile=profile;
profile=function(){
    const s=students.find(s=>s.id===profileId);let html=workspaceProfile();
    const template=document.createElement('template');template.innerHTML=html;
    const form=template.content.querySelector('#profile-edit-child');
    if(form){form.dataset.revision=s.revision;form.dataset.parentRevision=s.parent_revision||'';form.insertAdjacentHTML('beforeend','<fieldset class="body-space"><legend>المخولون باستلام الطفل</legend><div id="pickup-fields">'+pickupFields(s.pickups||[])+'</div><button type="button" class="secondary small" data-add-pickup>إضافة شخص</button><p class="muted">يمكن إزالة الشخص بمسح بياناته. الاسم والهاتف مطلوبان لكل شخص.</p></fieldset>');}
    if(s.pickups?.length)template.content.append(Object.assign(document.createElement('section'),{className:'panel',innerHTML:'<h2>المخولون بالاستلام</h2>'+s.pickups.map(p=>'<div class="list-card"><strong>'+esc(p.name)+'</strong><span>'+esc(p.phone)+' · '+esc(p.relation||'')+'</span></div>').join('')}));
    html=template.innerHTML;
    let actions='';
    if(s.cancelled&&canRestore())actions='<button class="secondary" data-restore="'+esc(s.id)+'">استرجاع الملف للمراجعة</button>';
    if(!s.cancelled&&s.account?.due&&liveSession.user.permissions.includes('accounts.delete')||!s.cancelled&&s.account?.due&&demoActor.admin)actions+='<button class="secondary danger" data-waiver="'+esc(s.id)+'">إسقاط الدين المستحق</button>';
    if(s.cancelled||s.paused)html+='<p class="notice-box">'+(s.cancelled?'ملف مؤرشف':'الاشتراك متوقف عند تاريخ المغادرة؛ استرجاع الملف لا يحتسب أشهر الغياب.')+'</p>';
    if(!s.cancelled&&!s.account&&(demoActor.admin||liveSession.user.permissions.includes('accounts.edit')))actions+='<button class="secondary" data-account-setup="'+esc(s.id)+'">تهيئة الاشتراك</button>';
    return html+(actions?'<div class="panel actions">'+actions+'</div>':'');
};
function pickupFields(items){return items.map(p=>'<div class="form-grid pickup-row"><label>الاسم<input name="pickup-name" maxlength="100" value="'+esc(p.name||'')+'"></label><label>الهاتف<input name="pickup-phone" maxlength="30" value="'+esc(p.phone||'')+'"></label><label>صلة القرابة<input name="pickup-relation" maxlength="100" value="'+esc(p.relation||'')+'"></label></div>').join('');}
function summaryWindow(label){
    const o=liveData.overview;if(!o)return;
    let body='',target='';
    if(label==='الطلاب الحاليون'){
        body=detailLine('الطلاب الحاليون',o.students_count)+detailLine('الملفات المؤرشفة',o.archived_students||0);
        target=demoCan('students')?'<button class="secondary" data-summary-go="students">فتح الطلاب</button>':'';
    }else if(['إجمالي المقبوضات','أطفال سددوا التسجيل','جيليه مدفوعة'].includes(label)){
        body=detailLine('المقبوض للتسجيل',o.registration_cash)+detailLine('المقبوض للجيليه',o.gilet_cash)+detailLine('المقبوض للشهور',o.monthly_cash)+detailLine('إجمالي النقد المقبوض',o.total_cash)+detailLine('أطفال سددوا التسجيل',o.registration_children)+detailLine('جيليه مدفوعة',o.gilet_count);
        if(demoCan('receipts')){body+=detailLine('عدد الوصولات السارية',receipts.filter(r=>!r.cancelled).length);target='<button class="secondary" data-summary-go="payments">فتح الوصولات</button>';}
    }else if(label==='إجمالي المصروفات')body=detailLine('المصروفات التشغيلية',o.operational_cash)+detailLine('الرواتب المدفوعة',o.salary_cash)+detailLine('السلف المدفوعة',o.advance_cash)+detailLine('إجمالي النقد المصروف',o.expenses);
    else if(label==='الباقي من المداخيل')body=detailLine('المقبوض',o.total_cash)+detailLine('المصروف',o.expenses)+detailLine('الباقي النقدي',o.remaining_cash)+'<p class="muted">ديون الطلاب ليست نقدًا مقبوضًا.</p>';
    else body=detailLine('المستحق على الطلاب الآن',o.due_now)+'<p class="muted">يشمل الدين المحفوظ على المعفي والمؤرشف. لا تتضمن القيمة رسوم الشهور التي لم تستحق بعد.</p>'+(demoCan('students')?'<button class="secondary" data-summary-go="archives">مراجعة الأرشيف</button>':'');
    openProtected(label,'<div class="summary-detail">'+body+'</div>'+target);
}
function tableChoices(){return (liveData.tools||[]).map(t=>'<option value="'+t.key+'" '+(toolTable===t.key?'selected':'')+'>'+esc(t.title)+'</option>').join('');}
function toolsScreen(){
    const can=p=>demoActor.admin||liveSession.user.permissions.includes(p);
    const tabs=[['records','الملفات والأدوات',!!liveData.tools?.length],['fees','الرسوم',can('fees.view')],['payroll','الرواتب والسلف',can('salaries.view')],['reports','التقارير',can('reports.view')],['backup','نسخة البيانات',demoActor.admin]];
    if(!tabs.some(t=>t[0]===toolTab&&t[2]))toolTab=tabs.find(t=>t[2])?.[0]||'none';
    let html=heading('إدارة الروضة','الأدوات المفيدة داخل الواجهة نفسها، حسب صلاحياتك.')+'<div class="workspace-nav">'+tabs.filter(t=>t[2]).map(([key,label])=>'<button class="secondary" data-tool-tab="'+key+'" aria-selected="'+(toolTab===key)+'">'+label+'</button>').join('')+'</div>';
    if(toolTab==='records'){
        if(!liveData.tools.some(t=>t.key===toolTable))toolTable=liveData.tools[0].key;
        const config=liveData.tools.find(t=>t.key===toolTable);
        html+='<div class="panel"><div class="list-controls"><label>القائمة<select id="tool-table">'+tableChoices()+'</select></label><label>بحث<input id="tool-search" value="'+esc(toolQuery)+'"></label><label class="check-row"><input id="tool-archived" type="checkbox" '+(toolArchived?'checked':'')+'>إظهار المؤرشف والملغى</label>'+(config.create?'<button class="secondary" id="tool-create">إضافة</button>':'')+'</div><div id="tool-rows">'+toolRowsHTML()+'</div></div>';
    }else if(toolTab==='fees')html+='<div class="panel" id="fees-view">'+(feeDraft?'<div class="stats">'+Object.entries({registration:'التسجيل',gilet:'الجيليه',tuition:'الشهرية'}).map(([k,v])=>stat('💵',v,money(feeDraft.values[k]),'أوقية قديمة')).join('')+'</div>'+(can('fees.edit')?'<button class="secondary body-space" id="edit-fees">تعديل الرسوم</button>':''):'<p class="tools-pending">جارٍ تحميل الرسوم…</p>')+'</div>';
    else if(toolTab==='payroll')html=html+payrollScreen(can);
    else if(toolTab==='reports')html+=reportScreen();
    else if(toolTab==='backup')html+='<div class="panel"><h2>تصدير شامل للبيانات</h2><p class="muted body-space">يشمل الجداول والصور الحالية وسجل التغييرات وملفات تحقق. هذه بيانات خاصة بالمدير؛ الملف تصدير بيانات، وليس نسخة PostgreSQL جاهزة للاستعادة.</p><a class="secondary body-space" href="/api/download/backup">تنزيل ZIP الشامل</a></div>';
    return html;
}
function toolRowsHTML(){
    if(!toolRows)return '<p class="tools-pending">جارٍ التحميل…</p>';
    const config=liveData.tools.find(t=>t.key===toolTable);
    return toolRows.items.map(r=>'<div class="list-card"><div><strong>'+esc(r.title)+'</strong><small>'+esc(Object.entries(r.values).filter(([k,v])=>v!==null&&v!==''&&['mobile','salary','salary_month','amount','item_name','start_date','status','father_mobile','mother_mobile'].includes(k)).map(([k,v])=>(config.fields.find(f=>f.key===k)?.label||k)+': '+(v==='exempt'?'معفي':v==='regular'?'عادي':v)).join(' · '))+'</small>'+(r.cash!==null&&r.cash!==undefined?'<small>النقد المدفوع: '+money(r.cash)+' · المستند: '+(r.document==='active'?'سارٍ':'ملغى')+'</small>':'')+'</div><div class="actions">'+(!r.cancelled?((config.edit?'<button class="secondary small" data-tool-id="'+esc(r.id)+'" data-tool-mode="edit">تعديل</button>':'')+(config.delete?'<button class="secondary small danger" data-tool-id="'+esc(r.id)+'" data-tool-mode="cancel">إلغاء الإدخال</button>':'')+(config.delete&&toolTable.startsWith('teacher_')&&r.document==='active'?'<button class="secondary small" data-tool-id="'+esc(r.id)+'" data-tool-mode="void_document">إلغاء المستند فقط</button>':'')):'<span class="status amber">مؤرشف / ملغى</span>')+'</div></div>').join('')+'<div class="pager"><button class="secondary" data-tool-page="-1" '+(toolRows.page===1?'disabled':'')+'>السابق</button><span>'+toolRows.page+' / '+toolRows.pages+' · '+toolRows.total+'</span><button class="secondary" data-tool-page="1" '+(toolRows.page===toolRows.pages?'disabled':'')+'>التالي</button></div>';
}
let toolFetch=0;
async function loadToolRows(){
    const version=++toolFetch,table=toolTable;
    try{const data=await liveCall('tools.list',{table,query:toolQuery,page:toolPage,archived:toolArchived});if(version!==toolFetch||table!==toolTable)return;toolRows=data;if($('#tool-rows'))$('#tool-rows').innerHTML=toolRowsHTML();}
    catch(e){if(version===toolFetch)toast(e.message,'error');}
}
function fieldInput(f,value=''){
    const val=value??'';
    return '<label>'+esc(f.label)+(f.required?' *':'')+(f.type==='select'?'<select name="'+f.key+'">'+f.choices.map(v=>'<option value="'+v+'" '+(v===val?'selected':'')+'>'+(v==='regular'?'عادي':v==='exempt'?'معفي':esc(v))+'</option>').join('')+'</select>':'<input name="'+f.key+'" type="'+f.type+'" '+(f.required?'required':'')+' '+(f.type==='number'?'step="0.01" min="0"':'maxlength="2000"')+' value="'+esc(val)+'">')+'</label>';
}
function toolEditor(id,mode){
    const config=liveData.tools.find(t=>t.key===toolTable),r=toolRows?.items.find(r=>String(r.id)===String(id));
    const values=r?.values||{};
    if(mode==='create')for(const f of config.fields)values[f.key]=f.type==='date'?today:f.type==='number'?(f.key==='quantity'?1:0):'';
    const cash=toolTable.startsWith('teacher_');
    let note=mode==='void_document'?'يُلغى المستند فقط ويبقى النقد المصروف محسوبًا.':mode==='cancel'&&cash?'إلغاء إدخال مالي خاطئ: يُزال أثر النقد من الحسابات، مع حفظ الأصل وسجل التغيير.':mode==='cancel'?'يُؤرشف السجل مع حفظ البيانات والتاريخ.':cash?'تصحيح إدخال خاطئ وليس صرف مبلغ إضافي.':'تُحفظ التعديلات مع السبب واسم المسؤول.';
    if(['classes','academic_years','registrations'].includes(toolTable))note+=' هذه سجلات النظام السابق؛ لا تغيّر مفاتيح الربط دون مراجعة، ولا تُحوّل وحداتها المالية القديمة تلقائيًا.';
    if(toolTable==='assets')note+=' تسجيل التجهيز في الجرد لا يخصم نقدًا؛ الصرف الفعلي يسجل كمصروف.';
    openProtected((mode==='create'?'إضافة':mode==='edit'?'تعديل':'إلغاء')+' · '+config.title,'<form id="tool-edit-form" data-mode="'+mode+'" data-id="'+esc(id||'')+'" data-table="'+toolTable+'" data-revision="'+esc(r?.revision||'')+'"><p class="archive-note">'+note+'</p>'+(mode==='edit'||mode==='create'?'<div class="form-grid body-space">'+config.fields.map(f=>fieldInput(f,values[f.key])).join('')+'</div>':'')+confirmation()+'</form>');
}
function teacherChoices(){return '<option value="">اختر المعلمة…</option>'+teacherOptions.filter(t=>!t.archived).map(t=>'<option value="'+esc(t.id)+'">'+esc(t.name+' · '+t.identity)+'</option>').join('');}
function payrollScreen(can){
    return '<div class="panel"><h2>الرواتب والسلف</h2><p class="muted body-space">للرواتب والسلف سجلان مستقلان. إلغاء المستند مع بقاء النقد يختلف عن إلغاء الإدخال المالي الخاطئ.</p><div class="actions body-space"><button class="secondary" data-payroll-records="teacher_payments">سجل الرواتب</button><button class="secondary" data-payroll-records="teacher_advances">سجل السلف</button>'+(can('salaries.create')?'<button class="secondary" id="new-salary">صرف راتب</button><button class="secondary" id="new-advance">صرف سلفة</button>':'')+'</div></div>';
}
function salaryWindow(kind){
    openProtected(kind==='salary'?'صرف راتب':'صرف سلفة','<form id="payroll-form" data-kind="'+kind+'"><label>المعلمة<select name="teacher" required>'+teacherChoices()+'</select></label><div class="form-grid body-space">'+fieldInput({key:'month',label:'الشهر',type:'month',required:true},today.slice(0,7))+fieldInput({key:'date',label:'تاريخ الصرف',type:'date',required:true},today)+(kind==='salary'?fieldInput({key:'base',label:'الراتب الأساسي',type:'number',required:true},0)+fieldInput({key:'bonus',label:'مكافأة',type:'number'},0)+fieldInput({key:'deductions',label:'خصومات',type:'number'},0):fieldInput({key:'amount',label:'مبلغ السلفة',type:'number',required:true},0))+'</div><p class="notice-box" id="salary-net">الصافي: 0 أوقية</p><label>ملاحظات<input name="notes"></label>'+confirmation()+'</form>');
    const form=$('#payroll-form');const update=()=>{$('#salary-net').textContent='الصافي: '+money(kind==='salary'?Number(form.elements.base.value)+Number(form.elements.bonus.value)-Number(form.elements.deductions.value):Number(form.elements.amount.value))+' أوقية قديمة';};
    form.oninput=update;form.elements.teacher.onchange=()=>{if(kind==='salary')form.elements.base.value=teacherOptions.find(t=>t.id===form.elements.teacher.value)?.salary||0;update();};
}
const summaryLabels={registration_cash:'قبض التسجيل',gilet_cash:'قبض الجيليه',monthly_cash:'قبض الشهرية',prepaid_cash:'المدفوع مقدمًا',total_cash:'إجمالي المقبوض',new_cash:'المقبوض خلال الفترة',operational_cash:'مصروفات تشغيلية',salary_cash:'رواتب مدفوعة',advance_cash:'سلف مدفوعة',expenses:'إجمالي المصروف',remaining_cash:'الباقي النقدي',due_now:'المستحق على الطلاب',registration_children:'أطفال سددوا التسجيل',gilet_count:'جيليه مدفوعة'};
function reportScreen(){
    const options={finance:'الحركة المالية خلال فترة'};
    for(const [key,title,area] of [['students','الطلاب والأقسام','students'],['debt','المتبقي على الطلاب','receipts'],['expenses','فواتير المصروفات','expenses'],['salaries','الرواتب المصروفة','salaries']])if(demoCan(area))options[key]=title;
    return '<form id="report-form" class="panel"><div class="form-grid"><label>التقرير<select name="kind">'+Object.entries(options).map(([k,v])=>'<option value="'+k+'" '+(reportRequest?.kind===k?'selected':'')+'>'+v+'</option>').join('')+'</select></label>'+fieldInput({key:'start',label:'من تاريخ',type:'date',required:true},reportRequest?.start||today.slice(0,8)+'01')+fieldInput({key:'end',label:'إلى تاريخ',type:'date',required:true},reportRequest?.end||today)+'<label>المعلمة لتقرير الرواتب<select name="teacher"><option value="">الكل</option>'+teacherOptions.map(t=>'<option value="'+esc(t.id)+'" '+(reportRequest?.teacher===t.id?'selected':'')+'>'+esc(t.name+' · '+t.identity+(t.archived?' · مؤرشفة':''))+'</option>').join('')+'</select></label></div><button class="secondary body-space">عرض التقرير</button><p class="error" role="alert"></p></form><p class="muted">قائمة الطلاب تعرض الملفات الحالية. تقرير المتبقي يحسب الدين إلى تاريخ النهاية، وفواتير المصروفات تُختار بتاريخ الفاتورة مع عرض مدفوعها التراكمي.</p><section id="report-output">'+reportHTML()+'</section>';
}
function reportHTML(){if(!reportData)return '';const items=reportData.items,keys=items.length?Object.keys(items[0]):[];return '<div class="panel"><div class="actions"><button class="secondary" id="report-xlsx">تنزيل Excel</button><button class="secondary" id="report-print">طباعة</button></div><div class="report-values body-space">'+Object.entries(reportData.summary).filter(([key])=>key!=='new_cash').map(([k,v])=>detailLine(summaryLabels[k]||k,v)).join('')+'</div>'+(keys.length?'<div class="table-wrap body-space"><table><thead><tr>'+keys.map(k=>'<th>'+esc(k)+'</th>').join('')+'</tr></thead><tbody>'+items.map(r=>'<tr>'+keys.map(k=>'<td>'+esc(r[k]??'—')+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<p class="muted body-space">لا توجد صفوف إضافية.</p>')+'</div>';}
showHistory=function(){
    const type=$('#history-type').value,action=$('#history-action').value,term=searchText($('#history-search').value);
    const rows=changes.filter(x=>(!type||x.type===type)&&(!action||x.action===action)&&searchText(JSON.stringify(x)).includes(term)).slice().reverse();
    const value=v=>v===null||v===undefined?'—':typeof v==='object'?JSON.stringify(v):String(v);
    const html=pageSlice('history',rows,rs=>rs.map(x=>{
        const before=x.before||{},after=x.after||{},fields=[...new Set([...Object.keys(before),...Object.keys(after)])].filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k])&&!['request_token','request_hash'].includes(k));
        const title=after.full_name||after.name||after.category||after.item_name||before.full_name||before.name||before.category||x.key;
        return '<details class="history-entry"><summary><span class="status">'+esc(actionNames[x.action]||x.action)+'</span> '+esc(recordNames[x.type]||x.type)+' · '+esc(title)+'</summary><p class="muted">'+esc(x.time)+' · '+esc(x.actor)+'</p><p>السبب: '+esc(x.reason||'—')+'</p><div class="history-diff">'+fields.map(k=>'<div><strong>'+esc(liveData.field_labels[k]||historyFields[k]||k)+'</strong><span>'+esc(value(before[k]))+'</span><span>←</span><span>'+esc(value(after[k]))+'</span></div>').join('')+'</div></details>';
    }).join(''));
    $('#history-rows').innerHTML=html+pager('history');
};
const workspaceRender=render;
render=function(){
    if(!liveSession||!liveData)return;
    if(page==='receipt'||page==='archives'||page==='tools'){
        $('#crumb').textContent=page==='receipt'?'الوصل':page==='archives'?'الأرشيف':'إدارة الروضة';
        $('#content').innerHTML=page==='receipt'?receiptScreen():page==='archives'?archiveScreen():toolsScreen();
        document.querySelectorAll('nav [data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page===(page==='archives'?'students':page==='receipt'?'payments':page));});
        bindRecordButtons();
    }else workspaceRender();
    $('#live-extra-nav')?.remove();
    if(!$('#nav-workspace')&&(liveData.tools?.length||demoActor.admin||liveSession.user.permissions.some(p=>['fees.view','reports.view','salaries.view'].includes(p)))){
        const button=document.createElement('button');button.id='nav-workspace';button.dataset.page='tools';button.textContent='⚙️ إدارة الروضة';button.onclick=()=>{navigate('tools');loadWorkspace();};
        document.querySelector('nav').insertBefore(button,$('#demo-logout'));
    }
    if($('#nav-workspace')){$('#nav-workspace').hidden=false;$('#nav-workspace').classList.toggle('active',page==='tools');}
    if(page==='students'&&!profileId&&demoCan('students')){
        const headingBox=$('#content .page-heading .actions')||$('#content .page-heading');
        if(!$('#open-archive')){const b=document.createElement('button');b.id='open-archive';b.className='secondary';b.textContent='الطلاب المؤرشفون';b.onclick=()=>navigate('archives');headingBox?.append(b);}
    }
    if(page==='dashboard'){
        document.querySelectorAll('#content [data-profile]').forEach(b=>{if(students.find(s=>s.id===b.dataset.profile)?.cancelled)b.closest('.receipt-row')?.remove();});
        document.querySelectorAll('#content .stat').forEach(card=>{const label=card.querySelector('.stat-label')?.textContent.trim();if(['الطلاب الحاليون','إجمالي المقبوضات','إجمالي المصروفات','الباقي من المداخيل','الباقي على الطلاب','أطفال سددوا التسجيل','جيليه مدفوعة'].includes(label)){card.setAttribute('role','button');card.tabIndex=0;card.onclick=()=>summaryWindow(label);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();summaryWindow(label);}};}});
    }
    const receiptToggle=$('#receipt-archived');if(receiptToggle)receiptToggle.onchange=()=>{includeArchivedReceipts=receiptToggle.checked;$('#receipt-rows').innerHTML=receiptRows();bindReceiptRows();};
    const archiveInput=$('#archive-search');if(archiveInput)archiveInput.oninput=event=>{archiveScreen.query=event.target.value;const position=event.target.selectionStart;$('#content').innerHTML=archiveScreen();const next=$('#archive-search');next.focus();next.setSelectionRange(position,position);next.oninput=archiveInput.oninput;};
    const rosterSearch=$('#student-search');if(rosterSearch)rosterSearch.oninput=e=>{$('#student-rows').innerHTML=studentRows(students.filter(s=>!s.cancelled&&childMatches(s,e.target.value)));bindProfiles();};
    bindWorkspaceInputs();
};
async function loadWorkspace(){
    try{
        if(toolTab==='records'){toolRows=null;await loadToolRows();}
        if(toolTab==='fees'){feeDraft=await liveCall('fees.read');if(page==='tools'&&toolTab==='fees')render();}
        if((toolTab==='payroll'||toolTab==='reports')&&demoCan('salaries')){teacherOptions=await liveCall('teachers.options');if(page==='tools')render();}
    }catch(e){toast(e.message,'error');}
}
function bindWorkspaceInputs(){
    const picker=$('#tool-table');if(picker)picker.onchange=()=>{toolTable=picker.value;toolPage=1;toolQuery='';toolRows=null;render();loadToolRows();};
    const search=$('#tool-search');if(search)search.oninput=()=>{toolQuery=search.value;toolPage=1;loadToolRows();};
    const archived=$('#tool-archived');if(archived)archived.onchange=()=>{toolArchived=archived.checked;toolPage=1;loadToolRows();};
    const expense=$('#expense-search');if(expense)expense.oninput=()=>{expenseTerm=expense.value;const pos=expense.selectionStart;render();const next=$('#expense-search');next.focus();next.setSelectionRange(pos,pos);};
}
const workspaceSubmit=liveSubmit;
liveSubmit=async function(form){
    const d=new FormData(form),get=k=>String(d.get(k)||'');
    if(form.id==='profile-edit-child'){
        const pickups=[...form.querySelectorAll('.pickup-row')].map(row=>({name:row.querySelector('[name="pickup-name"]').value,phone:row.querySelector('[name="pickup-phone"]').value,relation:row.querySelector('[name="pickup-relation"]').value}));
        return liveSaved('students.edit',{id:profileId,revision:form.dataset.revision,parent_revision:form.dataset.parentRevision,values:{...Object.fromEntries([...d].filter(([k,v])=>typeof v==='string')),pickups},reason:'تعديل بيانات الطالب من ملفه'},form);
    }
    if(form.id==='settlement-form')return liveSaved('expenses.settle',{id:Number(form.dataset.id),revision:form.dataset.revision,amount:get('amount'),date:get('date'),reason:get('reason'),confirmed:d.has('confirmed')},form);
    if(form.id==='account-setup-form')return liveSaved('accounts.setup',{student:form.dataset.student,start:get('start'),status:get('status'),confirmed:d.has('confirmed')},form);
    if(form.id==='restore-form')return liveSaved('students.restore',{student:form.dataset.student,revision:form.dataset.revision,account_revision:form.dataset.accountRevision||null,reason:get('reason'),confirmed:d.has('confirmed')},form);
    if(form.id==='waiver-form')return liveSaved('students.waive',{student:form.dataset.student,revision:Number(form.dataset.revision),due:form.dataset.due,reason:get('reason'),confirmed:d.has('confirmed')},form);
    if(form.id==='tool-edit-form'){
        const config=liveData.tools.find(t=>t.key===form.dataset.table),values={};
        for(const f of config.fields)if(d.has(f.key))values[f.key]=get(f.key);
        toolRows=null;
        const result=await liveSaved('tools.change',{table:form.dataset.table,id:form.dataset.id,mode:form.dataset.mode,revision:form.dataset.revision,values,reason:get('reason'),confirmed:d.has('confirmed')},form);
        loadToolRows();return result;
    }
    if(form.id==='fees-edit-form'){await liveSaved('fees.save',{registration:get('registration'),gilet:get('gilet'),tuition:get('tuition'),revision:form.dataset.revision,reason:get('reason'),confirmed:d.has('confirmed')},form);feeDraft=await liveCall('fees.read');render();return;}
    if(form.id==='payroll-form')return liveSaved('payroll.save',{kind:form.dataset.kind,teacher:get('teacher'),month:get('month'),date:get('date'),base:get('base'),bonus:get('bonus')||'0',deductions:get('deductions')||'0',amount:get('amount'),notes:get('notes'),confirmed:d.has('confirmed')},form);
    if(form.id==='report-form'){
        const request={kind:get('kind'),start:get('start'),end:get('end'),teacher:get('teacher')};
        const result=await liveCall('reports.read',request);reportData=result;reportRequest=request;$('#report-output').innerHTML=reportHTML();toast('تم إعداد التقرير.');return;
    }
    return workspaceSubmit(form);
};
document.addEventListener('click',async e=>{
    const target=e.target.closest('button');if(!target)return;
    const handle=()=>{e.preventDefault();e.stopImmediatePropagation();};
    if(target.hasAttribute('data-add-pickup')){handle();const container=$('#pickup-fields');if(container.children.length>=12){toast('الحد 12 شخصًا.','error');return;}container.insertAdjacentHTML('beforeend',pickupFields([{}]));return;}
    if(target.dataset.list){handle();const kind=target.dataset.list,s=listState.get(kind);s.page+=Number(target.dataset.delta);if(kind==='students'){$('#student-rows').innerHTML=studentRows(s.rows);bindProfiles();}else if(kind==='receipts'){$('#receipt-rows').innerHTML=receiptRows();bindReceiptRows();}else if(kind==='history')showHistory();else render();return;}
    if(target.hasAttribute('data-return-receipts')){handle();financeTab='receipts';navigate('payments');return;}
    if(target.hasAttribute('data-back-active')){handle();studentMode='list';navigate('students');return;}
    if(target.dataset.archiveProfile){handle();profileId=target.dataset.archiveProfile;page='students';render();pageTop();return;}
    if(target.dataset.restore){handle();restoreWindow(target.dataset.restore);return;}
    if(target.dataset.settle){handle();const x=expenses.find(x=>String(x.id)===target.dataset.settle);openProtected('تسديد متبقي المصروف','<form id="settlement-form" data-id="'+x.id+'" data-revision="'+esc(x.revision)+'"><p>المتبقي: '+money(x.amount-x.paid)+' أوقية قديمة. هذا صرف نقدي جديد؛ تصحيح إدخال خاطئ يتم من زر التعديل.</p><div class="form-grid">'+fieldInput({key:'amount',label:'المبلغ المدفوع الآن',type:'number',required:true},x.amount-x.paid)+fieldInput({key:'date',label:'تاريخ الصرف',type:'date',required:true},today)+'</div>'+confirmation()+'</form>');return;}
    if(target.dataset.accountSetup){handle();openProtected('تهيئة اشتراك طالب سابق','<form id="account-setup-form" data-student="'+esc(target.dataset.accountSetup)+'"><p class="notice-box">لا يضيف هذا الإجراء قبضًا. تاريخ البداية يحدد الأشهر المستحقة؛ لا يمكن تهيئة حساب له وصولات تاريخية تلقائيًا.</p>'+fieldInput({key:'start',label:'بداية الاشتراك',type:'date',required:true},today)+'<label>الحالة<select name="status"><option value="regular">دفع</option><option value="exempt">معفي</option></select></label>'+confirmation()+'</form>');return;}
    if(target.dataset.waiver){handle();waiverWindow(target.dataset.waiver);return;}
    if(target.dataset.summaryGo){handle();$('#record-dialog').close();if(target.dataset.summaryGo==='payments')financeTab='receipts';navigate(target.dataset.summaryGo);return;}
    if(target.dataset.toolTab){handle();toolTab=target.dataset.toolTab;render();pageTop();loadWorkspace();return;}
    if(target.dataset.toolPage){handle();toolPage+=Number(target.dataset.toolPage);loadToolRows();pageTop();return;}
    if(target.dataset.toolMode){handle();toolEditor(target.dataset.toolId,target.dataset.toolMode);return;}
    if(target.id==='tool-create'){handle();toolEditor(null,'create');return;}
    if(target.dataset.payrollRecords){handle();toolTable=target.dataset.payrollRecords;toolTab='records';toolPage=1;toolRows=null;render();loadToolRows();return;}
    if(target.id==='new-salary'||target.id==='new-advance'){handle();try{teacherOptions=await liveCall('teachers.options');salaryWindow(target.id==='new-salary'?'salary':'advance');}catch(error){toast(error.message,'error');}return;}
    if(target.id==='edit-fees'){handle();openProtected('تعديل الرسوم','<form id="fees-edit-form" data-revision="'+esc(feeDraft.revision)+'"><p class="archive-note">تظل أسعار الأشهر السابقة محفوظة؛ الأسعار الجديدة للفترات الجديدة.</p><div class="form-grid">'+Object.entries({registration:'التسجيل',gilet:'الجيليه',tuition:'الشهرية'}).map(([key,label])=>fieldInput({key,label,type:'number',required:true},feeDraft.values[key])).join('')+'</div>'+confirmation()+'</form>');return;}
    if(target.id==='report-print'){handle();window.print();return;}
    if(target.id==='report-xlsx'){
        handle();target.disabled=true;
        try{const response=await fetch('/api/reports.export',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf},body:JSON.stringify(reportRequest)});if(!response.ok)throw Error((await response.json()).error);const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='report.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);toast('تم إعداد ملف Excel.');}catch(error){toast(error.message,'error');}finally{target.disabled=false;}
    }
},true);
// Profile clicks from existing renderers also start the new screen at its top.
document.addEventListener('click',e=>{if(e.target.closest('[data-profile],#back-students,[data-finance]'))requestAnimationFrame(pageTop);});

// The session can finish loading before this optional script on slow networks.
if(liveSession&&liveData)render();
