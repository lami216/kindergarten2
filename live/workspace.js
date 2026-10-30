/* A single live workspace. All writes still go through the authorized bridge. */
'use strict';
let receiptPageId=null,toolTab='fees',toolTable='parents',toolRows=null,toolQuery='',toolPage=1,toolArchived=false;
let feeDraft=null,teacherOptions=[],reportData=null,reportRequest=null,reportExport=null;
const listState=new Map();let noticeTimer;
const workspaceCall=liveCall;
liveCall=async function(operation,data){
    const identity=liveSession,result=await workspaceCall(operation,data);
    if(identity&&identity!==liveSession&&!['login','session'].includes(operation))throw Error(`${I18N.tr("ui.598385eda54f")}`);
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
function pager(kind){const s=listState.get(kind);return !s?'' : `<div class="pager"><button type="button" class="secondary" data-list="${kind}" data-delta="-1" ${s.page===1?'disabled':''}>${I18N.tr("ui.a9e9d067101a")}</button><span>${I18N.tr("ui.77334549457e",{p0:s.page,p1:s.pages,p2:s.rows.length})}</span><button type="button" class="secondary" data-list="${kind}" data-delta="1" ${s.page===s.pages?'disabled':''}>${I18N.tr("ui.5cf7af74fd3a")}</button></div>`;}
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
        return `<div class="list-card" data-receipt-row="${r.id}"><div class="row-person">${studentAvatar(s)}<div><strong>${esc(s.name)}</strong><small>${I18N.tr("ui.bd9628ee2920",{p0:r.id,p1:esc(r.date),p2:s.cancelled?` ${I18N.tr("ui.f1a581eef6bf")}`:''})}</small></div></div><div class="actions"><span class="status ${r.cancelled?'amber':''}">${I18N.tr("ui.cb786d585e2d",{p0:money(r.amount),p1:r.cancelled?` ${I18N.tr("ui.0b82a8e63244")}`:''})}</span><button class="secondary small" data-receipt="${r.id}">${I18N.tr("ui.566dbcea7afa")}</button></div></div>`;
    }).join('')||`<div class="empty">${I18N.tr("ui.e9325c1ddd94")}</div>`);
    return html+pager('receipts');
};
paymentOptions=function(term=''){return `<option value="">${I18N.tr("ui.933ca4c3edbc")}</option>${students.filter(s=>!s.cancelled&&childMatches(s,term)).map(s=>'<option value="'+esc(s.id)+'">'+esc([s.name,s.parent,s.phone].filter(Boolean).join(' · '))+'</option>').join('')}`;};
const workspaceReceiptList=receiptList;
receiptList=()=>workspaceReceiptList().replace('</label>',`</label><label class="check-row body-space"><input type="checkbox" id="receipt-archived" ${includeArchivedReceipts?'checked':''}>${I18N.tr("ui.66af593f13d7")}</label>`);
openReceipt=function(id){receiptPageId=Number(id);page='receipt';render();pageTop();};
function receiptScreen(){
    const r=receipts.find(r=>r.id===receiptPageId),s=r&&students.find(s=>s.id===r.student);
    if(!r||!s)return heading(`${I18N.tr("ui.5d24240aeff3")}`,`${I18N.tr("ui.765c140c65f9")}`,`<button class="secondary" data-return-receipts>${I18N.tr("ui.ceb9efa64a1f")}</button>`);
    return `${heading(`${I18N.tr("ui.78ba4b68be77",{p0:r.id})}`,`${I18N.tr("ui.df3c75fa3c0e")}`,`<button class="secondary" data-return-receipts>${I18N.tr("ui.ceb9efa64a1f")}</button>`)}<section class="panel page-receipt" id="receipt-page"><span class="badge">${I18N.tr("ui.06aacc984eba")}</span>${r.cancelled?`<p class="notice-box">${I18N.tr("ui.5a65d9be6038")}</p>`:''}<div class="row-person body-space">${studentAvatar(s)}<div><h2>${esc(s.name)}</h2><p class="muted">${esc(s.parent)} · ${esc(s.phone)}</p></div></div><p>${I18N.tr("ui.a17de5e4aec4",{p0:esc(r.date)})}</p><div class="receipt-total">${money(r.amount)} <small>${I18N.tr("ui.894811c10b8d")}</small></div><div class="summary-detail">${detailLine(`${I18N.tr("ui.7dd297215d19")}`,r.registration)}${detailLine(`${I18N.tr("ui.c0a240e22598")}`,r.gilet)}${detailLine(`${I18N.tr("ui.e00922512362")}`,r.monthly)}</div><div class="actions"><a class="secondary" href="/api/receipt/${r.id}" target="_blank" rel="noopener">${I18N.tr("ui.47eb54fb2cf4")}</a>${recordActions('receipts',r.id,r.cancelled)}</div></section>`;
}
let expenseTerm='';
const workspaceExpensePage=expensePage;
expensePage=function(){
    const t=document.createElement('template');t.innerHTML=workspaceExpensePage();
    [...t.content.querySelectorAll('h2')].find(h=>h.textContent.includes(`${I18N.tr("ui.a94c5a0e6c01")}`))?.closest('.panel')?.remove();
    const table=t.content.querySelector('table');
    if(table){
        table.querySelector('thead tr').insertAdjacentHTML('beforeend',`<th>${I18N.tr("ui.9200595fd0fe")}</th>`);
        const rows=expenses.filter(e=>!e.cancelled&&searchText(e.category+' '+e.payee).includes(searchText(expenseTerm))).slice().reverse();
        const html=pageSlice('expenses',rows,rs=>rs.map(e=>'<tr><td>'+esc(e.category)+'<small>'+esc(e.payee)+'</small></td><td>'+money(e.amount)+'</td><td>'+money(e.paid)+'</td><td>'+money(e.amount-e.paid)+'</td><td>'+recordActions('expenses',e.id)+(e.amount>e.paid&&demoCan('expenses','edit')?`<button class="secondary small" data-settle="${e.id}">${I18N.tr("ui.b12f5645cbcc")}</button>`:'')+'</td></tr>').join(''));
        table.querySelector('tbody').innerHTML=html+'<tr><td colspan="5">'+pager('expenses')+'</td></tr>';
        table.closest('.table-wrap').insertAdjacentHTML('beforebegin',`<label class="body-space">${I18N.tr("ui.c34706c9bf43")}<input id="expense-search" value="${esc(expenseTerm)}" placeholder="${I18N.tr("ui.e44ca6e77ab3")}"></label>`);
    }
    return t.innerHTML;
};
function detailLine(label,value){return '<div class="summary-line"><span>'+esc(label)+'</span><strong>'+esc(typeof value==='number'?money(value):value)+'</strong></div>';}
demoGrantFields=function(prefix,permissions=[]){
    return Object.entries(liveData.resources).map(([area,resource])=>'<fieldset class="grant-row"><legend>'+esc(I18N.sourceLabel(resource.title))+'</legend>'+resource.actions.map(action=>{
        const value=uiPermission(area+'.'+action),label=demoActions[action==='delete'?'cancel':action];
        return '<label class="check-row"><input type="checkbox" name="grant" value="'+value+'" '+(permissions.includes(value)?'checked':'')+'>'+label+'</label>';
    }).join('')+'</fieldset>').join('');
};
liveGrants=function(values){return [...new Set(values.map(livePermission))];};
demoShowMetrics=function(){
    const user=demoUsers.find(u=>u.id===$('#demo-activity-user').value),m=demoMetrics(user);
    const labels=user.permissions.map(p=>{const server=livePermission(p),[area,action]=server.split('.');return I18N.sourceLabel(liveData.resources[area]?.title||area)+': '+(demoActions[action==='delete'?'cancel':action]||action);});
    $('#demo-activity-body').innerHTML='<p class="muted">'+esc(user.admin?`${I18N.tr("ui.71b8637823f9")}`:labels.join(`${I18N.tr("ui.bc4d631526af")} `)||`${I18N.tr("ui.b69fafc9d9c7")}`)+'</p><div class="stats">'+stat('🎒','طلاب سجلهم',m.students)+stat('📦','مصروفات سجلها',m.expenses)+stat('💵','صافي مصروفاته',money(m.cash),'أوقية قديمة')+stat('🧾','دفعات سجلها',m.payments)+stat('✏️','تعديلات محفوظة',m.edits)+stat('🕘','إلغاءات محفوظة',m.cancellations)+'</div>';
};
function archiveScreen(){
    const input=archiveScreen.query||'',rows=students.filter(s=>s.cancelled&&childMatches(s,input));
    const html=pageSlice('archives',rows,rs=>rs.map(s=>`<div class="list-card"><div class="row-person">${studentAvatar(s)}<div><strong>${esc(s.name)}</strong><small>${esc(s.parent)} · ${esc(s.phone)}</small></div></div><div class="actions"><button class="secondary small" data-archive-profile="${esc(s.id)}">${I18N.tr("ui.b5ba49dd5f73")}</button>${canRestore()?`<button class="secondary small" data-restore="${esc(s.id)}">${I18N.tr("ui.41c88d959d57")}</button>`:''}</div></div>`).join('')||`<div class="empty">${I18N.tr("ui.99eacb2dec0f")}</div>`);
    return `${heading(`${I18N.tr("ui.66981cf53742")}`,`${I18N.tr("ui.f269eeee68d3")}`,`<button class="secondary" data-back-active>${I18N.tr("ui.e88c75392bba")}</button>`)}<div class="panel"><label>${I18N.tr("ui.17a50b597424")}<input id="archive-search" value="${esc(input)}" placeholder="${I18N.tr("ui.f6a88989e182")}"></label><div id="archive-rows">${html}${pager('archives')}</div></div>`;
}
function openProtected(title,body){
    $('#record-content').innerHTML=`<div class="dialog-head"><h2>${esc(title)}</h2><button type="button" class="quiet" id="workspace-close" aria-label="${I18N.tr("ui.ca90c297b099")}">✕</button></div>${body}`;
    const d=$('#record-dialog');d.showModal();protectEditWindow(d,['workspace-close']);
}
function confirmation(){return `<label class="body-space">${I18N.tr("ui.36c0f78bca45")}<input name="reason" required maxlength="2000"></label><label class="check-row"><input type="checkbox" name="confirmed" required>${I18N.tr("ui.8f7fa39dd786")}</label><p class="error" role="alert"></p><button class="primary body-space">${I18N.tr("ui.3cf39514bffb")}</button>`;}
function canRestore(){return demoCan('students','edit')&&(demoActor.admin||liveSession.user.permissions.includes('accounts.edit'));}
function restoreWindow(id){
    const s=students.find(s=>s.id===id);
    openProtected(`${I18N.tr("ui.80e9cb2ca97e",{p0:s.name})}`,`<form id="restore-form" data-student="${esc(id)}"><p class="archive-note">${I18N.tr("ui.ceae2c2086ca")}</p>${confirmation()}</form>`);
    $('#restore-form').dataset.revision=s.revision;$('#restore-form').dataset.accountRevision=s.account_revision||'';
}
function waiverWindow(id){
    const s=students.find(s=>s.id===id);
    if(!s.account?.due){toast(`${I18N.tr("ui.151ee314dfa8")}`);return;}
    openProtected(`${I18N.tr("ui.67bd138f73cf",{p0:s.name})}`,`<form id="waiver-form" data-student="${esc(id)}"><p>${I18N.tr("ui.2dd21f542b47")} <strong>${I18N.tr("ui.ce271d72c3a1",{p0:money(s.account.due)})}</strong></p><p class="archive-note">${I18N.tr("ui.47b1cfbf6c61")}</p>${confirmation()}</form>`);
    Object.assign($('#waiver-form').dataset,{due:String(s.account.due),revision:String(s.ledger_revision)});
}
const workspaceProfile=profile;
profile=function(){
    const s=students.find(s=>s.id===profileId);let html=workspaceProfile();
    const template=document.createElement('template');template.innerHTML=html;
    const financePanel=template.content.querySelector('#profile-receipts')?.closest('section');
    if(financePanel&&s.start)financePanel.insertAdjacentHTML('beforeend',`<p class="muted body-space subscription-anchor-note">${I18N.tr('payments.subscriptionAnchor',{date:esc(I18N.date(s.start))})}</p>`);
    const form=template.content.querySelector('#profile-edit-child');
    if(form){form.dataset.revision=s.revision;form.dataset.parentRevision=s.parent_revision||'';form.insertAdjacentHTML('beforeend',`<fieldset class="body-space"><legend>${I18N.tr("ui.108b2e28b04d")}</legend><div id="pickup-fields">${pickupFields(s.pickups||[])}</div><button type="button" class="secondary small" data-add-pickup>${I18N.tr("ui.4cdf6e2b8128")}</button><p class="muted">${I18N.tr("ui.e0821e7da378")}</p></fieldset>`);}
    if(form&&s.parent_id&&(demoActor.admin||liveSession.user.permissions.includes('parents.edit'))){
        const fields=[['fatherName','ui.3c571949c936',100],['fatherPhone','ui.a84e401aadf5',20],['motherName','ui.529a1e93a7ba',100],['motherPhone','ui.faee701516d5',20]];
        form.querySelector('.form-grid.body-space').insertAdjacentHTML('beforebegin',`<fieldset class="body-space profile-parents"><legend>${I18N.tr('ui.b3c275aa6ea2')}</legend><p class="muted">${I18N.tr('profile.parentsShared')}</p><div class="form-grid">${fields.map(([key,label,max])=>`<label>${I18N.tr(label)}<input name="${key}" maxlength="${max}" ${key.endsWith('Phone')?'type="tel" dir="ltr" autocomplete="tel"':''} value="${esc(s[key]||'')}"></label>`).join('')}</div></fieldset>`);
    }
    if(s.pickups?.length)template.content.append(Object.assign(document.createElement('section'),{className:'panel',innerHTML:`<h2>${I18N.tr("ui.52167851614e")}</h2>${s.pickups.map(p=>'<div class="list-card"><strong>'+esc(p.name)+'</strong><span>'+esc(p.phone)+' · '+esc(p.relation||'')+'</span></div>').join('')}`}));
    html=template.innerHTML;
    let actions='';
    if(s.cancelled&&canRestore())actions=`<button class="secondary" data-restore="${esc(s.id)}">${I18N.tr("ui.fcf370d37189")}</button>`;
    if(!s.cancelled&&s.account?.due&&liveSession.user.permissions.includes('accounts.delete')||!s.cancelled&&s.account?.due&&demoActor.admin)actions+=`<button class="secondary danger" data-waiver="${esc(s.id)}">${I18N.tr("ui.16a7ecb9bb55")}</button>`;
    if(s.cancelled||s.paused)html+='<p class="notice-box">'+(s.cancelled?`${I18N.tr("ui.37c1ba82c1de")}`:`${I18N.tr("ui.b3a8a223b7cd")}`)+'</p>';
    if(!s.cancelled&&!s.account&&(demoActor.admin||liveSession.user.permissions.includes('accounts.edit')))actions+=`<button class="secondary" data-account-setup="${esc(s.id)}">${I18N.tr("ui.329b7f8e6642")}</button>`;
    return html+(actions?'<div class="panel actions">'+actions+'</div>':'');
};
function pickupFields(items){return items.map(p=>`<div class="form-grid pickup-row"><label>${I18N.tr("ui.52ab09847cf8")}<input name="pickup-name" maxlength="100" value="${esc(p.name||'')}"></label><label>${I18N.tr("ui.94b59a5125fb")}<input name="pickup-phone" maxlength="30" value="${esc(p.phone||'')}"></label><label>${I18N.tr("ui.110dff56aee4")}<input name="pickup-relation" maxlength="100" value="${esc(p.relation||'')}"></label></div>`).join('');}
function summaryWindow(label){
    const o=liveData.overview;if(!o)return;
    let body='',target='';
    if(label===`${I18N.tr("ui.e88c75392bba")}`){
        body=detailLine(`${I18N.tr("ui.e88c75392bba")}`,o.students_count)+detailLine(`${I18N.tr("ui.d71adf2da096")}`,o.archived_students||0);
        target=demoCan('students')?`<button class="secondary" data-summary-go="students">${I18N.tr("ui.591a28aae99e")}</button>`:'';
    }else if([`${I18N.tr("ui.d06ec6b8635e")}`,`${I18N.tr("ui.2b1b334f72c2")}`,`${I18N.tr("ui.996ecb25be62")}`].includes(label)){
        body=detailLine(`${I18N.tr("ui.953dcce35628")}`,o.registration_cash)+detailLine(`${I18N.tr("ui.723744f1f4fc")}`,o.gilet_cash)+detailLine(`${I18N.tr("ui.f0021314ed93")}`,o.monthly_cash)+detailLine(`${I18N.tr("ui.a4cead0577d7")}`,o.total_cash)+detailLine(`${I18N.tr("ui.2b1b334f72c2")}`,o.registration_children)+detailLine(`${I18N.tr("ui.996ecb25be62")}`,o.gilet_count);
        if(demoCan('receipts')){body+=detailLine(`${I18N.tr("ui.7e45862ea3f6")}`,receipts.filter(r=>!r.cancelled).length);target=`<button class="secondary" data-summary-go="payments">${I18N.tr("ui.8087ddf8d19f")}</button>`;}
    }else if(label===`${I18N.tr("ui.03a4c3145ccb")}`)body=detailLine(`${I18N.tr("ui.05719604bbc0")}`,o.operational_cash)+detailLine(`${I18N.tr("ui.269aacd1a347")}`,o.salary_cash)+detailLine(`${I18N.tr("ui.55244d0200a4")}`,o.advance_cash)+detailLine(`${I18N.tr("ui.f079daad4277")}`,o.expenses);
    else if(label===`${I18N.tr("ui.9d3241abd96d")}`)body=`${detailLine(`${I18N.tr("ui.b2a9205830ba")}`,o.total_cash)+detailLine(`${I18N.tr("ui.b040e8a39096")}`,o.expenses)+detailLine(`${I18N.tr("ui.e447a5a85420")}`,o.remaining_cash)}<p class="muted">${I18N.tr("ui.af25d84a488b")}</p>`;
    else body=`${detailLine(`${I18N.tr("ui.842b3dd035eb")}`,o.due_now)}<p class="muted">${I18N.tr("ui.46464d6a3610")}</p>${demoCan('students')?`<button class="secondary" data-summary-go="archives">${I18N.tr("ui.b76f4138b2e4")}</button>`:''}`;
    openProtected(label,'<div class="summary-detail">'+body+'</div>'+target);
}
function visibleToolTables(){return (liveData.tools||[]).filter(t=>t.key!=='teachers');}
function tableChoices(){return visibleToolTables().map(t=>'<option value="'+t.key+'" '+(toolTable===t.key?'selected':'')+'>'+esc(I18N.sourceLabel(t.title))+'</option>').join('');}
function toolsScreen(){
    const can=p=>demoActor.admin||liveSession.user.permissions.includes(p);
    const tabs=[['records',`${I18N.tr("ui.70bdde6cdca8")}`,!!visibleToolTables().length],['fees',`${I18N.tr("ui.8bf5e54fbd8b")}`,can('fees.view')],['payroll',`${I18N.tr("ui.941f706ac934")}`,can('salaries.view')],['backup',`${I18N.tr("ui.316127a3a455")}`,demoActor.admin]];
    if(!tabs.some(t=>t[0]===toolTab&&t[2]))toolTab=tabs.find(t=>t[2])?.[0]||'none';
    let html=heading(`${I18N.tr("ui.2a505c4c3257")}`,`${I18N.tr("ui.ba19d8330afd")}`)+'<div class="workspace-nav">'+tabs.filter(t=>t[2]).map(([key,label])=>'<button class="secondary" data-tool-tab="'+key+'" aria-selected="'+(toolTab===key)+'">'+label+'</button>').join('')+'</div>';
    if(toolTab==='records'){
        if(!visibleToolTables().some(t=>t.key===toolTable))toolTable=visibleToolTables()[0].key;
        const config=liveData.tools.find(t=>t.key===toolTable);
        html+=`<div class="panel"><div class="list-controls"><label>${I18N.tr("ui.6c197eab0340")}<select id="tool-table">${tableChoices()}</select></label><label>${I18N.tr("ui.d0f6edcf6d65")}<input id="tool-search" value="${esc(toolQuery)}"></label><label class="check-row"><input id="tool-archived" type="checkbox" ${toolArchived?'checked':''}>${I18N.tr("ui.c282565a1380")}</label>${config.create?`<button class="secondary" id="tool-create">${I18N.tr("ui.d52453ac627d")}</button>`:''}</div><div id="tool-rows">${toolRowsHTML()}</div></div>`;
    }else if(toolTab==='fees')html+='<div class="panel" id="fees-view">'+(feeDraft?'<div class="stats">'+Object.entries({registration:`${I18N.tr("ui.7dd297215d19")}`,gilet:`${I18N.tr("ui.c0a240e22598")}`,tuition:`${I18N.tr("ui.e00922512362")}`}).map(([k,v])=>stat('💵',v,money(feeDraft.values[k]),'أوقية قديمة')).join('')+'</div>'+(can('fees.edit')?`<button class="secondary body-space" id="edit-fees">${I18N.tr("ui.3d4af3ac7649")}</button>`:''):`<p class="tools-pending">${I18N.tr("ui.8e88075dcd44")}</p>`)+'</div>';
    else if(toolTab==='payroll')html=html+payrollScreen(can);
    else if(toolTab==='reports')html+=reportScreen();
    else if(toolTab==='backup')html+=`<div class="panel"><h2>${I18N.tr("ui.da5af308cd06")}</h2><p class="muted body-space">${I18N.tr("ui.ce675eb94f4e")}</p><a class="secondary body-space" href="/api/download/backup">${I18N.tr("ui.c9f3dc1faa8c")}</a></div>`;
    return html;
}
function toolRowsHTML(){
    if(!toolRows)return `<p class="tools-pending">${I18N.tr("ui.aa5ebc30e485")}</p>`;
    const config=liveData.tools.find(t=>t.key===toolTable);
    return `${toolRows.items.map(r=>'<div class="list-card"><div><strong>'+esc(r.title)+'</strong><small>'+esc(Object.entries(r.values).filter(([k,v])=>v!==null&&v!==''&&['mobile','salary','salary_month','amount','item_name','start_date','status','father_mobile','mother_mobile'].includes(k)).map(([k,v])=>I18N.sourceLabel(config.fields.find(f=>f.key===k)?.label||k)+': '+(v==='exempt'?I18N.enumLabel(v):v==='regular'?`${I18N.tr("ui.f3569af24500")}`:v)).join(' · '))+'</small>'+(r.cash!==null&&r.cash!==undefined?`<small>${I18N.tr("ui.871d2a115f40",{p0:money(r.cash),p1:r.document==='active'?`${I18N.tr("ui.72fd9c63a8c8")}`:`${I18N.tr("ui.ab7b6061c68c")}`})}</small>`:'')+'</div><div class="actions">'+(!r.cancelled?(config.edit?`<button class="secondary small" data-tool-id="${esc(r.id)}" data-tool-mode="edit">${I18N.tr("ui.113d570d6555")}</button>`:'')+(config.delete?`<button class="secondary small danger" data-tool-id="${esc(r.id)}" data-tool-mode="cancel">${I18N.tr("ui.5cb07da92792")}</button>`:'')+(config.delete&&toolTable.startsWith('teacher_')&&r.document==='active'?`<button class="secondary small" data-tool-id="${esc(r.id)}" data-tool-mode="void_document">${I18N.tr("ui.0120a5042bd1")}</button>`:''):`<span class="status amber">${I18N.tr("ui.d75ce9695999")}</span>`)+'</div></div>').join('')}<div class="pager"><button class="secondary" data-tool-page="-1" ${toolRows.page===1?'disabled':''}>${I18N.tr("ui.a9e9d067101a")}</button><span>${toolRows.page} / ${toolRows.pages} · ${toolRows.total}</span><button class="secondary" data-tool-page="1" ${toolRows.page===toolRows.pages?'disabled':''}>${I18N.tr("ui.5cf7af74fd3a")}</button></div>`;
}
let toolFetch=0;
async function loadToolRows(){
    const version=++toolFetch,table=toolTable;
    try{const data=await liveCall('tools.list',{table,query:toolQuery,page:toolPage,archived:toolArchived});if(version!==toolFetch||table!==toolTable)return;toolRows=data;if($('#tool-rows'))$('#tool-rows').innerHTML=toolRowsHTML();}
    catch(e){if(version===toolFetch)toast(e.message,'error');}
}
function fieldInput(f,value=''){
    const val=value??'';
    return '<label>'+esc(I18N.sourceLabel(f.label))+(f.required?' *':'')+(f.type==='select'?'<select name="'+f.key+'">'+f.choices.map(v=>'<option value="'+v+'" '+(v===val?'selected':'')+'>'+(v==='regular'?`${I18N.tr("ui.f3569af24500")}`:v==='exempt'?I18N.enumLabel(v):esc(I18N.enumLabel(v)))+'</option>').join('')+'</select>':'<input name="'+f.key+'" type="'+f.type+'" '+(f.required?'required':'')+' '+(f.type==='number'?'step="0.01" min="0"':'maxlength="2000"')+' value="'+esc(val)+'">')+'</label>';
}
function toolEditor(id,mode){
    const config=liveData.tools.find(t=>t.key===toolTable),r=toolRows?.items.find(r=>String(r.id)===String(id));
    const values=r?.values||{};
    if(mode==='create')for(const f of config.fields)values[f.key]=f.type==='date'?today:f.type==='number'?(f.key==='quantity'?1:0):'';
    const cash=toolTable.startsWith('teacher_');
    let note=mode==='void_document'?`${I18N.tr("ui.b4c233f37c8a")}`:mode==='cancel'&&cash?`${I18N.tr("ui.dd0557ff2f3a")}`:mode==='cancel'?`${I18N.tr("ui.fd912e4f567b")}`:cash?`${I18N.tr("ui.2408f2135634")}`:`${I18N.tr("ui.b1609b023df4")}`;
    if(['classes','academic_years','registrations'].includes(toolTable))note+=` ${I18N.tr("ui.1a2d16b09701")}`;
    if(toolTable==='assets')note+=` ${I18N.tr("ui.26aef77c5886")}`;
    openProtected((mode==='create'?`${I18N.tr("ui.d52453ac627d")}`:mode==='edit'?`${I18N.tr("ui.113d570d6555")}`:`${I18N.tr("ui.9a30dc2a96b8")}`)+' · '+I18N.sourceLabel(config.title),'<form id="tool-edit-form" data-mode="'+mode+'" data-id="'+esc(id||'')+'" data-table="'+toolTable+'" data-revision="'+esc(r?.revision||'')+'"><p class="archive-note">'+note+'</p>'+(mode==='edit'||mode==='create'?'<div class="form-grid body-space">'+config.fields.map(f=>fieldInput(f,values[f.key])).join('')+'</div>':'')+confirmation()+'</form>');
}
function teacherChoices(){return `<option value="">${I18N.tr("ui.a1d164bb8759")}</option>${teacherOptions.filter(t=>!t.archived).map(t=>'<option value="'+esc(t.id)+'">'+esc(t.name+' · '+t.identity)+'</option>').join('')}`;}
function payrollScreen(can){
    return `<div class="panel"><h2>${I18N.tr("ui.941f706ac934")}</h2><p class="muted body-space">${I18N.tr("ui.6e5a39e4e155")}</p><div class="actions body-space"><button class="secondary" data-payroll-records="teacher_payments">${I18N.tr("ui.f4c2e567cb9f")}</button><button class="secondary" data-payroll-records="teacher_advances">${I18N.tr("ui.8f790c84d26f")}</button>${can('salaries.create')?`<button class="secondary" id="new-salary">${I18N.tr("ui.fcd4e5636f6c")}</button><button class="secondary" id="new-advance">${I18N.tr("ui.2e645e9953b2")}</button>`:''}</div></div>`;
}
function salaryWindow(kind){
    openProtected(kind==='salary'?`${I18N.tr("ui.fcd4e5636f6c")}`:`${I18N.tr("ui.2e645e9953b2")}`,`<form id="payroll-form" data-kind="${kind}"><label>${I18N.tr("ui.04870e1fed4b")}<select name="teacher" required>${teacherChoices()}</select></label><div class="form-grid body-space">${fieldInput({key:'month',label:`${I18N.tr("ui.52d32bfb58c3")}`,type:'month',required:true},today.slice(0,7))}${fieldInput({key:'date',label:`${I18N.tr("ui.1de51d2cdd19")}`,type:'date',required:true},today)}${kind==='salary'?fieldInput({key:'base',label:`${I18N.tr("ui.73ad6b20ceb7")}`,type:'number',required:true},0)+fieldInput({key:'bonus',label:`${I18N.tr("ui.c396e6b8b30a")}`,type:'number'},0)+fieldInput({key:'deductions',label:`${I18N.tr("ui.f4927c145dfc")}`,type:'number'},0):fieldInput({key:'amount',label:`${I18N.tr("ui.a882d0ecfb58")}`,type:'number',required:true},0)}</div><p class="notice-box" id="salary-net">${I18N.tr("ui.8c7ae4c6c985")}</p><label>${I18N.tr("ui.d446d2dc6b81")}<input name="notes"></label>${confirmation()}</form>`);
    const form=$('#payroll-form');const update=()=>{$('#salary-net').textContent=`${I18N.tr("ui.964d4b1ea70b",{p0:money(kind==='salary'?Number(form.elements.base.value)+Number(form.elements.bonus.value)-Number(form.elements.deductions.value):Number(form.elements.amount.value))})}`;};
    form.oninput=update;form.elements.teacher.onchange=()=>{if(kind==='salary')form.elements.base.value=teacherOptions.find(t=>t.id===form.elements.teacher.value)?.salary||0;update();};
}
const summaryLabels={registration_cash:`${I18N.tr("ui.7fe8b06a4cc7")}`,gilet_cash:`${I18N.tr("ui.7de34c7a86b5")}`,monthly_cash:`${I18N.tr("ui.b2a3067e1414")}`,prepaid_cash:`${I18N.tr("ui.ffb1844cb319")}`,total_cash:`${I18N.tr("ui.8cdf8237d7ff")}`,new_cash:`${I18N.tr("ui.1d3dbd215200")}`,operational_cash:`${I18N.tr("ui.d3066a437004")}`,salary_cash:`${I18N.tr("ui.f46f9101d6c3")}`,advance_cash:`${I18N.tr("ui.8c2c17f894d7")}`,expenses:`${I18N.tr("ui.c9e37ad9e515")}`,remaining_cash:`${I18N.tr("ui.e447a5a85420")}`,due_now:`${I18N.tr("ui.6ce732bcb7a5")}`,registration_children:`${I18N.tr("ui.2b1b334f72c2")}`,gilet_count:`${I18N.tr("ui.996ecb25be62")}`};
function reportTeacherChoices(selected=''){return `<option value="">${I18N.tr("ui.65f276da33cf")}</option>${teacherOptions.map(t=>'<option value="'+esc(t.id)+'" '+(selected===t.id?'selected':'')+'>'+esc(t.name+' · '+t.identity+(t.archived?` ${I18N.tr("ui.542078432380")}`:''))+'</option>').join('')}`;}
function reportScreen(){
    const options={finance:`${I18N.tr("ui.f915274fc2c4")}`};
    for(const [key,title,area] of [['students',`${I18N.tr("ui.c56e2f31629f")}`,'students'],['debt',`${I18N.tr("ui.219dfac6a29b")}`,'receipts'],['expenses',`${I18N.tr("ui.eac7e1b9ac20")}`,'expenses'],['salaries',`${I18N.tr("ui.c3cf6edd07ce")}`,'salaries']])if(demoCan(area))options[key]=title;
    return `<form id="report-form" class="panel"><div class="form-grid"><label>${I18N.tr("ui.a92dbae49f8a")}<select name="kind">${Object.entries(options).map(([k,v])=>'<option value="'+k+'" '+(reportRequest?.kind===k?'selected':'')+'>'+v+'</option>').join('')}</select></label>${fieldInput({key:'start',label:`${I18N.tr("ui.996988dbc52e")}`,type:'date',required:true},reportRequest?.start||today.slice(0,8)+'01')}${fieldInput({key:'end',label:`${I18N.tr("ui.217caed1c04f")}`,type:'date',required:true},reportRequest?.end||today)}<label>${I18N.tr("ui.36813b4e8159")}<select name="teacher">${reportTeacherChoices(reportRequest?.teacher)}</select></label></div><button class="secondary body-space">${I18N.tr("ui.92ad0d774e56")}</button><p class="error" role="alert"></p></form><p class="muted">${I18N.tr("ui.d4787e96d6a3")}</p><section id="report-output">${reportHTML()}</section>`;
}
function reportHTML(){if(!reportData)return '';const items=reportData.items,keys=items.length?Object.keys(items[0]):[];return `<div class="panel"><div class="actions"><button class="secondary" id="report-xlsx">${I18N.tr("ui.e422937f6626")}</button><button class="secondary" id="report-print">${I18N.tr("ui.2e00e00acffe")}</button></div><div class="report-values body-space">${Object.entries(reportData.summary).filter(([key])=>key!=='new_cash').map(([k,v])=>detailLine(summaryLabels[k]||k,v)).join('')}</div>${keys.length?'<div class="table-wrap body-space"><table><thead><tr>'+keys.map(k=>'<th>'+esc(I18N.sourceLabel(k))+'</th>').join('')+'</tr></thead><tbody>'+items.map(r=>'<tr>'+keys.map(k=>'<td>'+esc(['الحالة','حالة المستند'].includes(k)?I18N.enumLabel(r[k]??'—'):(r[k]??'—'))+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':`<p class="muted body-space">${I18N.tr("ui.b02536bda450")}</p>`}</div>`;}
showHistory=function(){
    const type=$('#history-type').value,action=$('#history-action').value,term=searchText($('#history-search').value);
    const rows=changes.filter(x=>(!type||x.type===type)&&(!action||x.action===action)&&searchText(JSON.stringify(x)).includes(term)).slice().reverse();
    const value=(v,k)=>v===null||v===undefined?'—':typeof v==='object'?JSON.stringify(v):(['status','gender','payment_method','state','record_state'].includes(k)?I18N.enumLabel(v):String(v));
    const html=pageSlice('history',rows,rs=>rs.map(x=>{
        const before=x.before||{},after=x.after||{},fields=[...new Set([...Object.keys(before),...Object.keys(after)])].filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k])&&!['request_token','request_hash',...(x.type.endsWith('_attendance')?['attendance_id','person_id','department_id','revision','updated_at','cancelled_at']:[])].includes(k));
        const title=after.full_name||after.name||after.category||after.item_name||before.full_name||before.name||before.category||x.key;
        return `<details class="history-entry"><summary><span class="status">${esc(actionNames[x.action]||x.action)}</span> ${esc(recordNames[x.type]||x.type)} · ${esc(title)}</summary><p class="muted">${esc(x.time)} · ${esc(x.actor)}</p><p>${I18N.tr("ui.c7395544de8d",{p0:esc(x.reason||'—')})}</p><div class="history-diff">${fields.map(k=>'<div><strong>'+esc(I18N.fieldLabel(k,liveData.field_labels[k]||historyFields[k]||k))+'</strong><span>'+esc(value(before[k],k))+'</span><span>'+(I18N.lang==='fr'?'→':'←')+'</span><span>'+esc(value(after[k],k))+'</span></div>').join('')}</div></details>`;
    }).join(''));
    $('#history-rows').innerHTML=html+pager('history');
};
const workspaceRender=render;
render=function(){
    if(!liveSession||!liveData)return;
    if(page==='receipt'||page==='archives'||page==='tools'){
        $('#crumb').textContent=page==='receipt'?`${I18N.tr("ui.5d24240aeff3")}`:page==='archives'?`${I18N.tr("ui.8c5cae641943")}`:`${I18N.tr("ui.2a505c4c3257")}`;
        $('#content').innerHTML=page==='receipt'?receiptScreen():page==='archives'?archiveScreen():toolsScreen();
        document.querySelectorAll('nav [data-page]').forEach(b=>{b.classList.toggle('active',b.dataset.page===(page==='archives'?'students':page==='receipt'?'payments':page));});
        bindRecordButtons();
    }else workspaceRender();
    $('#live-extra-nav')?.remove();
    if(!$('#nav-workspace')&&(liveData.tools?.length||demoActor.admin||liveSession.user.permissions.some(p=>['fees.view','salaries.view'].includes(p)))){
        const button=document.createElement('button');button.id='nav-workspace';button.dataset.page='tools';button.textContent=`${I18N.tr("ui.382057f38b2e")}`;button.onclick=()=>{navigate('tools');loadWorkspace();};
        document.querySelector('nav').insertBefore(button,$('#demo-logout'));
    }
    if($('#nav-workspace')){$('#nav-workspace').hidden=false;$('#nav-workspace').classList.toggle('active',page==='tools');}
    if(page==='students'&&!profileId&&demoCan('students')){
        const headingBox=$('#content .page-heading .actions')||$('#content .page-heading');
        if(!$('#open-archive')){const b=document.createElement('button');b.id='open-archive';b.className='secondary';b.textContent=`${I18N.tr("ui.66981cf53742")}`;b.onclick=()=>navigate('archives');headingBox?.append(b);}
    }
    if(page==='dashboard'){
        document.querySelectorAll('#content [data-profile]').forEach(b=>{if(students.find(s=>s.id===b.dataset.profile)?.cancelled)b.closest('.receipt-row')?.remove();});
        document.querySelectorAll('#content .stat').forEach(card=>{const label=card.querySelector('.stat-label')?.textContent.trim();if([`${I18N.tr("ui.e88c75392bba")}`,`${I18N.tr("ui.d06ec6b8635e")}`,`${I18N.tr("ui.03a4c3145ccb")}`,`${I18N.tr("ui.9d3241abd96d")}`,`${I18N.tr("ui.1a02c0e12c4c")}`,`${I18N.tr("ui.2b1b334f72c2")}`,`${I18N.tr("ui.996ecb25be62")}`].includes(label)){card.setAttribute('role','button');card.tabIndex=0;card.onclick=()=>summaryWindow(label);card.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();summaryWindow(label);}};}});
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
        if((toolTab==='payroll'||toolTab==='reports')&&demoCan('salaries')){
            const tab=toolTab,options=await liveCall('teachers.options');teacherOptions=options;
            // Updating a lookup must not rebuild a form the user is filling in.
            if(page==='tools'&&toolTab===tab&&tab==='reports'){
                const picker=$('#report-form [name="teacher"]');
                if(picker)picker.innerHTML=reportTeacherChoices(picker.value);
            }
        }
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
        const values={...Object.fromEntries([...d].filter(([k,v])=>typeof v==='string')),pickups};
        for(const key of ['fatherName','fatherPhone','motherName','motherPhone']){const input=form.elements[key];if(input&&input.value.trim()===input.defaultValue.trim())delete values[key];}
        const start=form.elements.start_date;
        if(start&&start.value===form.dataset.subscriptionStart)delete values.start_date;
        return liveSaved('students.edit',{id:profileId,revision:form.dataset.revision,parent_revision:form.dataset.parentRevision,
            account_revision:form.dataset.accountRevision,ledger_revision:form.dataset.ledgerRevision===undefined?undefined:Number(form.dataset.ledgerRevision),
            values,reason:`${I18N.tr("ui.4141b5d2b7ab")}`},form);
    }
    if(form.id==='settlement-form')return liveSaved('expenses.settle',{id:Number(form.dataset.id),revision:form.dataset.revision,amount:get('amount'),date:get('date'),reason:get('reason'),confirmed:d.has('confirmed')},form);
    if(form.id==='account-setup-form')return liveSaved('accounts.setup',{student:form.dataset.student,start:get('start'),status:get('status'),confirmed:d.has('confirmed')},form);
    if(form.id==='restore-form')return liveSaved('students.restore',{student:form.dataset.student,revision:form.dataset.revision,account_revision:form.dataset.accountRevision||null,reason:get('reason'),confirmed:d.has('confirmed')},form);
    if(form.id==='waiver-form')return liveSaved('students.waive',{student:form.dataset.student,revision:Number(form.dataset.revision),due:form.dataset.due,reason:get('reason'),confirmed:d.has('confirmed')},form);
    if(form.id==='tool-edit-form'){
        const config=liveData.tools.find(t=>t.key===form.dataset.table),values={};
        for(const f of config.fields)if(d.has(f.key))values[f.key]=get(f.key);
        toolRows=null;
        const result=await liveSaved('tools.change',{table:form.dataset.table,id:form.dataset.id,mode:form.dataset.mode,revision:form.dataset.revision,values,reason:get('reason'),confirmed:d.has('confirmed'),due:form.dataset.exemptionDue===undefined?undefined:Number(form.dataset.exemptionDue),ledger_revision:form.dataset.exemptionLedger===undefined?undefined:Number(form.dataset.exemptionLedger)},form);
        loadToolRows();return result;
    }
    if(form.id==='fees-edit-form'){await liveSaved('fees.save',{registration:get('registration'),gilet:get('gilet'),tuition:get('tuition'),revision:form.dataset.revision,reason:get('reason'),confirmed:d.has('confirmed')},form);feeDraft=await liveCall('fees.read');render();return;}
    if(form.id==='payroll-form')return liveSaved('payroll.save',{kind:form.dataset.kind,teacher:get('teacher'),month:get('month'),date:get('date'),base:get('base'),bonus:get('bonus')||'0',deductions:get('deductions')||'0',amount:get('amount'),notes:get('notes'),confirmed:d.has('confirmed')},form);
    if(form.id==='report-form'){
        const request={kind:get('kind'),start:get('start'),end:get('end'),teacher:get('teacher')};
        const result=await liveCall('reports.read',request);reportData=result;reportRequest=request;$('#report-output').innerHTML=reportHTML();toast(`${I18N.tr("ui.9872db2390a4")}`);return;
    }
    return workspaceSubmit(form);
};
document.addEventListener('click',async e=>{
    const target=e.target.closest('button');if(!target)return;
    const handle=()=>{e.preventDefault();e.stopImmediatePropagation();};
    if(target.hasAttribute('data-add-pickup')){handle();const container=$('#pickup-fields');if(container.children.length>=12){toast(`${I18N.tr("ui.fdd109831559")}`,'error');return;}container.insertAdjacentHTML('beforeend',pickupFields([{}]));return;}
    if(target.dataset.list){handle();const kind=target.dataset.list,s=listState.get(kind);s.page+=Number(target.dataset.delta);if(kind==='students'){$('#student-rows').innerHTML=studentRows(s.rows);bindProfiles();}else if(kind==='receipts'){$('#receipt-rows').innerHTML=receiptRows();bindReceiptRows();}else if(kind==='history')showHistory();else render();return;}
    if(target.hasAttribute('data-return-receipts')){handle();financeTab='receipts';navigate('payments');return;}
    if(target.hasAttribute('data-back-active')){handle();studentMode='list';navigate('students');return;}
    if(target.dataset.archiveProfile){handle();profileId=target.dataset.archiveProfile;page='students';render();pageTop();return;}
    if(target.dataset.restore){handle();restoreWindow(target.dataset.restore);return;}
    if(target.dataset.settle){handle();const x=expenses.find(x=>String(x.id)===target.dataset.settle);openProtected(`${I18N.tr("ui.767331a12218")}`,`<form id="settlement-form" data-id="${x.id}" data-revision="${esc(x.revision)}"><p>${I18N.tr("ui.6005f325771c",{p0:money(x.amount-x.paid)})}</p><div class="form-grid">${fieldInput({key:'amount',label:`${I18N.tr("ui.3626e6063316")}`,type:'number',required:true},x.amount-x.paid)}${fieldInput({key:'date',label:`${I18N.tr("ui.1de51d2cdd19")}`,type:'date',required:true},today)}</div>${confirmation()}</form>`);return;}
    if(target.dataset.accountSetup){handle();openProtected(`${I18N.tr("ui.e2c11e28454d")}`,`<form id="account-setup-form" data-student="${esc(target.dataset.accountSetup)}"><p class="notice-box">${I18N.tr("ui.1be153852fae")}</p>${fieldInput({key:'start',label:`${I18N.tr("ui.e1e660e94889")}`,type:'date',required:true},today)}<label>${I18N.tr("ui.c3a4749caed4")}<select name="status"><option value="regular">${I18N.tr("ui.5e1b515f1b13")}</option><option value="exempt">${I18N.tr("ui.a3ae7c221c0f")}</option></select></label>${confirmation()}</form>`);return;}
    if(target.dataset.waiver){handle();waiverWindow(target.dataset.waiver);return;}
    if(target.dataset.summaryGo){handle();$('#record-dialog').close();if(target.dataset.summaryGo==='payments')financeTab='receipts';navigate(target.dataset.summaryGo);return;}
    if(target.dataset.toolTab){handle();toolTab=target.dataset.toolTab;render();pageTop();loadWorkspace();return;}
    if(target.dataset.toolPage){handle();toolPage+=Number(target.dataset.toolPage);loadToolRows();pageTop();return;}
    if(target.dataset.toolMode){handle();toolEditor(target.dataset.toolId,target.dataset.toolMode);return;}
    if(target.id==='tool-create'){handle();toolEditor(null,'create');return;}
    if(target.dataset.payrollRecords){handle();toolTable=target.dataset.payrollRecords;toolTab='records';toolPage=1;toolRows=null;render();loadToolRows();return;}
    if(target.id==='new-salary'||target.id==='new-advance'){handle();try{teacherOptions=await liveCall('teachers.options');salaryWindow(target.id==='new-salary'?'salary':'advance');}catch(error){toast(error.message,'error');}return;}
    if(target.id==='edit-fees'){handle();openProtected(`${I18N.tr("ui.3d4af3ac7649")}`,`<form id="fees-edit-form" data-revision="${esc(feeDraft.revision)}"><p class="archive-note">${I18N.tr("ui.ceac4c23aaf7")}</p><div class="form-grid">${Object.entries({registration:`${I18N.tr("ui.7dd297215d19")}`,gilet:`${I18N.tr("ui.c0a240e22598")}`,tuition:`${I18N.tr("ui.e00922512362")}`}).map(([key,label])=>fieldInput({key,label,type:'number',required:true},feeDraft.values[key])).join('')}</div>${confirmation()}</form>`);return;}
    if(target.id==='report-print'){handle();window.print();return;}
    if(target.id==='report-xlsx'){
        handle();target.disabled=true;
        try{const response=await fetch('/api/reports.export',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf},body:JSON.stringify(reportRequest)});if(!response.ok)throw Error((await response.json()).error);const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='report.xlsx';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);toast(`${I18N.tr("ui.712fbae77bc1")}`);}catch(error){toast(error.message,'error');}finally{target.disabled=false;}
    }
},true);
// Profile clicks from existing renderers also start the new screen at its top.
document.addEventListener('click',e=>{if(e.target.closest('[data-profile],#back-students,[data-finance]'))requestAnimationFrame(pageTop);});

// The session can finish loading before this optional script on slow networks.
if(liveSession&&liveData)render();
