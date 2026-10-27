/* Production binding for the ORIGINAL Pages renderers, not another UI.
 * No local accounts, local persistence, optimistic financial writes or demo data.
 * Every mutation awaits the existing Python services and reloads committed data.
 */
'use strict';
if (!window.LIVE_APP) throw Error('The live bridge is not a preview script.');
let liveSession=null, liveData=null, liveRecord=null, liveFee=null, livePreview=null;
const liveBusy=new WeakSet();
const liveAreas={receipts:'payments',dashboard:'reports'};
const livePermission=p=>{const [area,action]=p.split('.');return (liveAreas[area]||area)+'.'+(action==='cancel'?'delete':action);};
const uiPermission=p=>{const [area,action]=p.split('.');return ({payments:'receipts',reports:'dashboard'}[area]||area)+'.'+(action==='delete'?'cancel':action);};
const liveUser=u=>({id:String(u.user_id),name:u.employee_name,username:u.username,admin:u.is_admin,active:u.active,
    permissions:u.permissions.map(uiPermission),serverPermissions:u.permissions,version:u.auth_version});
function liveGrants(values,user){
    const selected=values.map(livePermission);
    const visible=new Set(Object.entries(demoAreas).flatMap(([area])=>(['dashboard','history'].includes(area)?['view']:Object.keys(demoActions)).map(a=>livePermission(area+'.'+a))));
    return [...new Set(selected.concat((user?.serverPermissions||[]).filter(p=>!visible.has(p))))];
}
async function liveCall(operation, data){
    const init={credentials:'same-origin',headers:{'X-App-Language':I18N.lang}};
    if(data!==undefined){init.method='POST';init.headers={'X-App-Language':I18N.lang,'Content-Type':'application/json','X-CSRF-Token':liveSession?.csrf||''};init.body=JSON.stringify(data);}
    const response=await fetch('/api/'+operation,init);
    let value;try{value=await response.json();}catch{throw Error(`${I18N.tr("ui.5578f8d51f5b")}`);}
    if(!response.ok){
        if(response.status===401||(response.status===403&&operation==='session'))liveLoginScreen();
        throw Error((value.language===I18N.lang?value.error:I18N.message(value.error))||`${I18N.tr("ui.f926c7fdd7e3")}`);
    }
    return value;
}
function liveLoginScreen(){
    liveSession=null;liveData=null;demoActor=null;
    students.splice(0);receipts.splice(0);expenses.splice(0);departments.splice(0);changes.splice(0);demoUsers.splice(0);demoAccountEvents.splice(0);studentPortraits.clear();
    document.querySelectorAll('dialog[open]').forEach(d=>d.close());
    document.body.classList.add('login-mode');$('#preview-login').hidden=false;$('#content').replaceChildren();
    $('#live-login [name="password"]').value='';
}
async function liveLoad(){
    const data=await liveCall('snapshot');liveData=data;
    students.splice(0,students.length,...data.students);
    receipts.splice(0,receipts.length,...data.receipts);
    expenses.splice(0,expenses.length,...data.expenses);
    departments.splice(0,departments.length,...data.departments.filter(d=>!d.cancelled).map(d=>d.name));
    changes.splice(0,changes.length,...data.changes.map(c=>{
        const aliases={school_departments:'departments',monthly_receipts:'receipts'};
        const convert=o=>{if(!o)return null;return {...o,name:o.full_name||o.name,category:o.category,student:o.student_id,
            amount:o.amount??o.amount_total,paid:o.amount_paid,date:o.received_on||o.expense_date,
            cancelled:o.state==='cancelled'||!!o.archived_at||!!o.cancelled_at};};
        return {...c,type:aliases[c.type]||c.type,before:convert(c.before),after:convert(c.after)};
    }));
    demoUsers.splice(0,demoUsers.length,...data.users.map(liveUser));
    demoAccountEvents.splice(0,demoAccountEvents.length,...data.account_events.map(e=>({action:e.action,name:e.target_name,actor:e.responsible})));
    studentPortraits.clear();students.forEach(s=>{if(s.photo)studentPortraits.set(s.id,s.photo);});
    document.body.classList.remove('login-mode');$('#preview-login').hidden=true;
}
async function liveEnter(){
    liveSession=await liveCall('session');demoActor=liveUser(liveSession.user);
    await liveLoad();render();
}
const liveAccount=account;
account=s=>s?.account?{...s.account,rs:receipts.filter(r=>r.student===s.id&&!r.cancelled)}:{paid:0,due:0,monthPaid:0,full:0,rs:[]};
const livePaymentBody=paymentBody;
paymentBody=function(s){
    const template=document.createElement('template');template.innerHTML=livePaymentBody(s);
    const fees=template.content.querySelector('details p');
    if(fees&&s.account){
        const label=(kind)=>s.account[kind+'_due']?`${I18N.tr("ui.d483582d2871",{p0:money(s.account[kind+'_due'])})}`:`${I18N.tr("ui.7d222428bc79")}`;
        fees.textContent=`${I18N.tr("ui.946a9f4b4fa8",{p0:label('registration'),p1:label('gilet')})}`;
    }
    return template.innerHTML;
};
const liveStatus=status;
status=s=>demoCan('receipts')?liveStatus(s):'<span class="muted">—</span>';
const liveStat=stat;
stat=function(icon,label,value,...rest){
    const keys={'الطلاب الحاليون':'students_count','إجمالي المقبوضات':'total_cash','إجمالي المصروفات':'expenses','الباقي من المداخيل':'remaining_cash',
        'الباقي على الطلاب':'due_now','أطفال سددوا التسجيل':'registration_children','جيليه مدفوعة':'gilet_count',
        'قبض التسجيل':'registration_cash','قبض الجيليه':'gilet_cash','قبض الشهرية':'monthly_cash'};
    if(liveData?.overview&&keys[label]){
        const raw=liveData.overview[keys[label]];value=['registration_children','gilet_count','students_count'].includes(keys[label])?raw:money(raw);
    }
    return liveStat(icon,label,value,...rest);
};
const liveRecordRows=recordRows;
recordRows=(type,include=false)=>type==='departments'?(liveData?.departments||[]).filter(d=>include||!d.cancelled):liveRecordRows(type,include);
const liveRecordActions=recordActions;
recordActions=(type,id,cancelled=false)=>{
    if(type==='departments')id=liveData?.departments.find(d=>d.name===id||String(d.id)===String(id))?.id??id;
    return liveRecordActions(type,id,cancelled);
};
const liveOpenRecord=openRecord;
openRecord=function(type,id,mode){
    const r=recordRows(type,true).find(r=>String(r.id)===String(id));
    liveRecord={type,id,mode,source:r?copy(r):null};
    liveOpenRecord(type,id,mode);
    if(type==='departments'&&r)$('#record-edit-form [name="destination"]')?.querySelectorAll('option').forEach(o=>{if(o.value===r.name)o.remove();});
    if(type==='students'&&$('#record-edit-form [name="class"]')){
        // Class assignment belongs to the existing atomic transfer window.
        $('#record-edit-form [name="class"]').disabled=true;
    }
};
const liveReceipt=openReceipt;
openReceipt=function(id){
    liveReceipt(id);
    const box=$('#receipt-content');
    const a=document.createElement('a');a.className='secondary body-space';a.textContent=`${I18N.tr("ui.9f595bc90670")}`;a.href='/api/receipt/'+encodeURIComponent(id);a.target='_blank';a.rel='noopener';box.append(a);
};
logChange=()=>{throw Error(`${I18N.tr("ui.9976d21def26")}`);};
demoMetrics=user=>{
    const m=liveData?.metrics[user.id];
    const activity=m?.activity||[];
    return {students:m?.students||0,expenses:m?.expenses.count||0,original:m?.expenses.original_cash||0,
        cash:m?.expenses.current_cash||0,payments:m?.payments.count||0,
        edits:activity.filter(a=>a.action==='updated').reduce((n,a)=>n+Number(a.events),0),
        cancellations:activity.filter(a=>['cancelled','deleted','archived'].includes(a.action)).reduce((n,a)=>n+Number(a.events),0)};
};
const anchoredPaymentBody=paymentBody;
paymentBody=function(student){
    const template=document.createElement('template');template.innerHTML=anchoredPaymentBody(student);
    const title=template.content.querySelector('#payment-form .form-title');
    if(title&&student.start)title.insertAdjacentHTML('afterend',`<p class="muted body-space subscription-anchor-note">${I18N.tr('payments.subscriptionAnchor',{date:esc(I18N.date(student.start))})}<br>${I18N.tr('payments.cashDateNote')}</p>`);
    return template.innerHTML;
};
const liveRender=render;
render=function(){
    if(!liveSession||!liveData)return;
    liveRender();
    if(!demoCan('students','create'))$('#home-student')?.remove();
    if(!demoCan('receipts','create'))document.querySelectorAll('#content [data-go="payments"]').forEach(e=>e.remove());
    if(!demoCan('expenses','create'))document.querySelectorAll('#content [data-go="expenses"]').forEach(e=>e.remove());
    if(page==='dashboard'&&!demoCan('receipts')){
        document.querySelectorAll('#content .two-col .panel').forEach(e=>e.remove());
    }
    document.querySelectorAll('.demo-scope-note').forEach(e=>e.remove());
    if(liveData.prices){
        const price=liveData.prices;
        const pay=$('#initial-payment');
        if(pay)for(const [key,label] of [['registration',`${I18N.tr("ui.6a8d48082bb7")}`],['gilet',`${I18N.tr("ui.c0a240e22598")}`]]){
            const input=pay.querySelector('[name="'+key+'"]');
            if(input){[...input.parentNode.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).forEach(n=>n.remove());input.after(` ${I18N.tr("ui.534c6752577e",{p0:label,p1:money(price[key])})}`);}
        }
        document.querySelectorAll('#payment-body .stat-hint').forEach(e=>{if(e.textContent.includes(`${I18N.tr("ui.8f2ef0ac6c3f")}`))e.textContent=`${I18N.tr("ui.7c49443cb433",{p0:money(price.tuition)})}`;});
    }
    const stale=$('#content #live-extra');if(stale)stale.remove();
    $('#live-extra-nav')?.remove();
    if(page==='history'){
        Object.assign(recordNames,{parents:`${I18N.tr("ui.c1cbf676c66a")}`,monthly_accounts:`${I18N.tr("ui.a622c6cc7dd4")}`,monthly_waivers:`${I18N.tr("ui.fad4906e939c")}`,
            monthly_tariffs:`${I18N.tr("ui.8bf5e54fbd8b")}`,student_departments:`${I18N.tr("ui.4da224329746")}`,department_transfers:`${I18N.tr("ui.e115b12155c8")}`,
            teacher_payments:`${I18N.tr("ui.8da58f1c866a")}`,teacher_advances:`${I18N.tr("ui.e20934947b9a")}`,teachers:`${I18N.tr("ui.4be8b769b898")}`,assets:`${I18N.tr("ui.a33f063e2607")}`,
            academic_years:`${I18N.tr("ui.c158104e0084")}`,classes:`${I18N.tr("ui.7a85fcf1e4f7")}`,registrations:`${I18N.tr("ui.6e17b9f7d430")}`,payments:`${I18N.tr("ui.9931c7e45a82")}`});
        actionNames.deleted=`${I18N.tr("ui.59ca629220a6")}`;actionNames.archived=`${I18N.tr("ui.fd59618fd6aa")}`;
        if(changes.length===500){const p=document.createElement('p');p.className='muted';p.textContent=`${I18N.tr("ui.31e2cf04d846")}`;$('#content').append(p);}
        showHistory();
    }
};
function liveError(form,error){
    let box=form.querySelector('.error');
    if(!box){box=document.createElement('p');box.className='error';box.setAttribute('role','alert');form.append(box);}
    box.textContent=error.message||`${I18N.tr("ui.46f641bc5808")}`;
}
async function liveFile(file){
    if(!file||!file.size)return null;
    if(file.size>5*1024*1024)throw Error(`${I18N.tr("ui.697fdd4ae2fd")}`);
    const bytes=new Uint8Array(await file.arrayBuffer());let result='';
    for(let n=0;n<bytes.length;n+=32768)result+=String.fromCharCode(...bytes.subarray(n,n+32768));
    return btoa(result);
}
async function liveSaved(operation,data,form){
    data.request_token=form.dataset.requestToken||(form.dataset.requestToken=crypto.randomUUID());
    const result=await liveCall(operation,data);
    try{await liveLoad();}catch{throw Error(`${I18N.tr("ui.ac8069d8f7fc")}`);}
    document.querySelectorAll('dialog[open]').forEach(d=>d.close());
    if(operation==='students.create'){studentMode='list';page='students';profileId=null;}
    render();toast(`${I18N.tr("ui.8f603dcbc07f")}`);return result;
}
async function liveSubmit(form){
    const d=new FormData(form),get=k=>String(d.get(k)||'');
    if(form.id==='live-login'){
        await liveCall('login',{username:get('username'),password:get('password')});form.reset();
        page='dashboard';profileId=null;studentMode='list';financeTab='payment';receiptChild=null;await liveEnter();return;
    }
    if(!liveSession)throw Error(`${I18N.tr("ui.1d385745f642")}`);
    if(form.id==='student-form')return liveSaved('students.create',{
        name:get('name'),birth:get('birth'),start_date:get('start_date')||undefined,gender:get('gender'),place:get('place'),address:get('address'),
        health:get('health'),father:get('father'),fatherPhone:get('fatherPhone'),mother:get('mother'),
        motherPhone:get('motherPhone'),existing_parent_id:get('existing_parent_id'),mode:get('mode'),registration:d.has('registration'),gilet:d.has('gilet'),
        amount:get('amount')||'0',photo:await liveFile(form.querySelector('[name="photo"]')?.files[0])},form);
    if(form.id==='profile-edit-child'||form.id==='edit-child'){
        const s=students.find(s=>s.id===profileId);
        return liveSaved('students.edit',{id:s.id,revision:s.revision,parent_revision:s.parent_revision,
            values:Object.fromEntries([...d].filter(([k,v])=>typeof v==='string')),
            reason:`${I18N.tr("ui.4141b5d2b7ab")}`},form);
    }
    if(form.id==='department-form')return liveSaved('departments.create',{name:get('name')},form);
    if(form.id==='transfer-form'){
        const department=liveData.departments.find(d=>!d.cancelled&&d.name===$('#department-destination').value);
        if(!department)throw Error(`${I18N.tr("ui.cedf78a7dd1a")}`);
        return liveSaved('departments.transfer',{ids:d.getAll('student').map(String),department_id:department.id},form);
    }
    if(form.id==='payment-form'){
        const amount=$('#pay-amount').value;
        if(!livePreview||livePreview.student!==receiptChild||livePreview.date!==get('date')||Number(amount)!==Number(livePreview.amount)||!$('#pay-agree')?.checked)throw Error(`${I18N.tr("ui.bdbd3c3fdc57")}`);
        return liveSaved('payments.create',{student:receiptChild,amount,date:get('date'),confirmed:true,
            revision:livePreview.revision,tariff:livePreview.tariff},form);
    }
    if(form.id==='fee-collect-form'){
        if(!liveFee||!d.has('agree'))throw Error(`${I18N.tr("ui.d673efea91ae")}`);
        return liveSaved('fees.collect',{...liveFee,date:get('date'),confirmed:true},form);
    }
    if(form.id==='expense-form'){
        const amount=get('amount'),status=get('status');
        return liveSaved('expenses.create',{category:get('category'),amount,paid:status==='full'?amount:status==='debt'?'0':get('paid'),
            date:get('date'),payee:get('payee'),notes:get('notes')},form);
    }
    if(form.id==='record-edit-form'){
        if(!liveRecord?.source||!d.has('agree'))throw Error(`${I18N.tr("ui.60357ba9aa94")}`);
        const s=liveRecord.source;
        const destination=liveData.departments.find(x=>!x.cancelled&&x.name===get('destination'));
        return liveSaved('records.change',{type:liveRecord.type,id:s.id,mode:liveRecord.mode,reason:get('reason'),
            revision:s.revision,parent_revision:s.parent_revision,values:Object.fromEntries([...d].filter(([k,v])=>typeof v==='string')),
            destination:destination?.id??null,confirmed:true},form);
    }
    if(form.id==='profile-photo-form'||form.id==='profile-photo-remove')return liveSaved('photos.save',{
        student:profileId,revision:Number(form.dataset.revision),reason:get('reason'),remove:form.id==='profile-photo-remove',
        confirmed:d.has('confirm'),photo:await liveFile(form.querySelector('[type="file"]')?.files[0])},form);
    if(form.id==='demo-user-create')return liveSaved('users.save',{name:get('name'),username:get('username'),
        password:get('password'),permissions:liveGrants(d.getAll('grant')),active:true},form);
    if(form.id==='demo-account-edit'){
        const u=demoUsers.find(u=>u.id===form.dataset.liveUser);
        if(!u)throw Error(`${I18N.tr("ui.f25e6c8a1788")}`);
        return liveSaved('users.save',{id:u.id,version:u.version,name:get('name'),password:get('password'),
            active:d.has('active'),permissions:liveGrants(d.getAll('grant'),u)},form);
    }
    throw Error(`${I18N.tr("ui.ea065aa114a5")}`);
}
document.addEventListener('submit',async event=>{
    const form=event.target;
    event.preventDefault();event.stopImmediatePropagation();
    if(!form.reportValidity()||liveBusy.has(form))return;
    liveBusy.add(form);const buttons=[...form.querySelectorAll('[type="submit"],button:not([type])')];buttons.forEach(b=>b.disabled=true);
    try{await liveSubmit(form);}catch(error){liveError(form,error);}finally{liveBusy.delete(form);buttons.forEach(b=>b.disabled=false);}
},true);
document.addEventListener('click',async event=>{
    const fee=event.target.closest('[data-collect-fee]');
    if(fee){const s=students.find(s=>s.id===fee.dataset.student);liveFee={student:s.id,kind:fee.dataset.collectFee,
        due:s.account[fee.dataset.collectFee+'_due']};}
    const preview=event.target.closest('#payment-preview-button');
    if(!preview)return;
    event.preventDefault();event.stopImmediatePropagation();
    livePreview=null;const amount=$('#pay-amount').value,student=receiptChild,on=$('#pay-date').value;
    if(!$('#payment-form').reportValidity())return;
    preview.disabled=true;
    try{
        const result=await liveCall('payments.preview',{student,amount,date:on});
        if(student!==receiptChild||amount!==$('#pay-amount')?.value||on!==$('#pay-date')?.value)return;
        livePreview={...result,student,date:on};
        $('#pay-preview').innerHTML=`<div class="payment-preview"><strong>${I18N.tr("ui.cfc87a02b937",{p0:esc(money(result.amount))})}</strong>${result.months.map(m=>`<p>${I18N.tr("ui.cbeb9ac49eea",{p0:esc(m.start),p1:esc(m.end),p2:esc(money(m.allocating))})}</p>`).join('')}<label class="check-row"><input id="pay-agree" type="checkbox"> ${I18N.tr("ui.bc3401d3860f")}</label><button class="primary" id="pay-save" disabled>${I18N.tr("ui.ee20bfe88097")}</button></div>`;
        $('#pay-agree').onchange=e=>$('#pay-save').disabled=!e.target.checked;
    }catch(error){toast(error.message);}finally{preview.disabled=false;}
},true);
const liveEditUser=demoEditUser;
demoEditUser=function(id){liveEditUser(id);$('#demo-account-edit').dataset.liveUser=id;};
// Choosing an existing family links siblings without overwriting its contacts.
// The option is only supplied to identities with students.view on the server.
const liveStudentForm=studentForm;
studentForm=function(){
    const template=document.createElement('template');template.innerHTML=liveStudentForm();
    if(liveData?.families?.length){
        const options=liveData.families.map(f=>{
            const label=[f.father||f.mother,f.fatherPhone||f.motherPhone,f.id].filter(Boolean).join(' · ');
            return '<option value="'+esc(f.id)+'">'+esc(label)+'</option>';
        }).join('');
        template.content.querySelectorAll('.student-section-title')[1].insertAdjacentHTML('afterend',
            `<label class="body-space">${I18N.tr("ui.eaf8cb4c49c7")}<select name="existing_parent_id"><option value="">${I18N.tr("ui.4561314eec16")}</option>${options}</select></label>`);
    }
    return template.innerHTML;
};
const liveBindStudentForm=bindStudentForm;
bindStudentForm=function(){
    liveBindStudentForm();
    const form=$('#student-form'),picker=form.querySelector('[name="existing_parent_id"]');
    if(!picker)return;
    const keys=['father','fatherPhone','mother','motherPhone'];let draft={};
    picker.onchange=()=>{
        const family=liveData.families.find(f=>f.id===picker.value);
        if(family&&!keys.some(k=>form.elements[k].disabled))draft=Object.fromEntries(keys.map(k=>[k,form.elements[k].value]));
        for(const key of keys){form.elements[key].disabled=!!family;form.elements[key].value=family?family[key]:(draft[key]||'');}
    };
};
$('#demo-logout').onclick=async()=>{try{await liveCall('logout',{});liveLoginScreen();}catch(e){toast(e.message);}};
// Retain the original card/logo/typography. Replace ONLY the demo entry with real credentials.
$('#demo-worker-login')?.closest('details')?.remove();
document.querySelectorAll('.demo-scope-note').forEach(e=>e.remove());
const enter=$('#preview-enter');enter.onclick=null;enter.textContent=`${I18N.tr("ui.beb869eecc12")}`;enter.type='submit';
const login=document.createElement('form');login.id='live-login';
const userLabel=document.createElement('label');userLabel.textContent=`${I18N.tr("ui.06668ac85e3d")}`;
const user=document.createElement('input');user.name='username';user.autocomplete='username';user.required=true;user.dir='ltr';userLabel.append(user);
const passLabel=document.createElement('label');passLabel.textContent=`${I18N.tr("ui.b05d306b5591")}`;
const pass=document.createElement('input');pass.name='password';pass.type='password';pass.autocomplete='current-password';pass.required=true;pass.maxLength=128;passLabel.append(pass);
enter.replaceWith(login);login.append(userLabel,passLabel,enter);
liveLoginScreen();
liveEnter().catch(error=>{if(liveSession)liveError(login,error);});
