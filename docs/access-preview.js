/* Synthetic, per-tab interaction model. Real authentication is in access_control.py. */
const demoUsers=[{id:'owner',name:'صاحب الروضة',username:'owner',admin:true,active:true,permissions:[]}];
const demoAccountEvents=[];
let demoActor=demoUsers[0];
const demoAreas={students:'الطلاب',receipts:'الدفعات والوصولات',expenses:'المصروفات',departments:'الأقسام',dashboard:'الملخص المالي الشامل',history:'سجل التغييرات الكامل'};
const demoActions={view:'عرض',create:'إضافة',edit:'تعديل',cancel:'إلغاء / حذف'};
const demoCan=(area,action='view')=>!!demoActor?.active&&(demoActor.admin||demoActor.permissions.includes(area+'.'+action));
function demoMayPage(target){const area={registration:'departments',payments:'receipts'}[target]||target;return target==='dashboard'||(target==='admin'?demoActor.admin:target==='records'?demoActor.admin:Object.keys(demoActions).some(a=>demoCan(area,a)));}

document.querySelector('nav').insertAdjacentHTML('beforeend','<button data-page="admin" id="nav-admin">🔐 <span>لوحة المدير</span></button><button id="demo-logout">🚪 <span>تسجيل الخروج</span></button>');
$('#nav-admin').onclick=()=>{if(demoActor.admin)navigate('admin');};
$('#demo-logout').onclick=demoLogout;
$('#preview-enter').textContent='معاينة لوحة المدير';
$('#preview-enter').onclick=()=>{demoActor=demoUsers[0];demoEnter();};
$('#preview-enter').insertAdjacentHTML('afterend',`<details class="demo-worker-login"><summary>دخول حساب عامل من المعاينة</summary><form id="demo-worker-login" class="body-space"><label>اسم المستخدم<input name="username" required autocomplete="off"></label><label class="body-space">كلمة المرور<input name="password" type="password" required autocomplete="off"></label><p class="error" id="demo-login-error" role="alert"></p><button class="primary body-space">تسجيل الدخول</button></form></details><p class="muted demo-scope-note">حسابات هذه المعاينة داخل التبويب فقط. لا تستخدم كلمة مرورك الحقيقية.</p>`);
async function demoHash(password,salt){const material=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveBits']);const bits=await crypto.subtle.deriveBits({name:'PBKDF2',salt:new TextEncoder().encode(salt),iterations:600000,hash:'SHA-256'},material,256);return Array.from(new Uint8Array(bits),b=>b.toString(16).padStart(2,'0')).join('');}
$('#demo-worker-login').onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target),user=demoUsers.find(u=>u.username===d.get('username').trim().toLowerCase()&&u.active&&!u.admin);if(!user||await demoHash(d.get('password'),user.salt)!==user.hash){$('#demo-login-error').textContent='تعذّر الدخول بهذه البيانات.';return;}demoActor=user;e.target.reset();demoEnter();};
function demoEnter(){document.body.classList.remove('login-mode');$('#preview-login').hidden=true;page='dashboard';profileId=null;studentMode='list';financeTab='payment';receiptChild=null;receiptSearch='';render();}
function demoLogout(){document.querySelectorAll('dialog[open]').forEach(d=>d.close());$('#content').replaceChildren();$('#sidebar').classList.remove('open');document.body.classList.add('login-mode');$('#preview-login').hidden=false;$('#demo-worker-login').reset();$('#demo-login-error').textContent='';demoActor=null;}

const demoBaseLog=logChange;
logChange=(...args)=>{demoBaseLog(...args);const event=changes.at(-1);event.actor=demoActor.username;event.actorId=demoActor.id;};
const demoBaseActions=recordActions;
recordActions=(type,id,cancelled=false)=>{if(cancelled)return demoBaseActions(type,id,true);const html=demoBaseActions(type,id,false);const box=document.createElement('div');box.innerHTML=html;box.querySelectorAll('[data-record-mode]').forEach(b=>{if(!demoCan(type,b.dataset.recordMode==='edit'?'edit':'cancel'))b.remove();});return box.innerHTML;};
const demoBaseRecord=openRecord;
openRecord=(type,id,mode)=>{if(demoCan(type,mode==='edit'?'edit':'cancel'))demoBaseRecord(type,id,mode);};

function demoGrantFields(prefix,permissions=[]){return Object.entries(demoAreas).map(([area,label])=>{const actions=['dashboard','history'].includes(area)?['view']:Object.keys(demoActions);return `<fieldset class="grant-row"><legend>${esc(label)}</legend>${actions.map(action=>`<label class="check-row"><input type="checkbox" name="grant" value="${area}.${action}" ${permissions.includes(area+'.'+action)?'checked':''}>${demoActions[action]}</label>`).join('')}</fieldset>`;}).join('');}
function demoNormalizeGrants(values){const grants=new Set(values);for(const value of values){const [area,action]=value.split('.');if(['edit','cancel'].includes(action))grants.add(area+'.view');}if(grants.has('receipts.create'))grants.add('receipts.view');return [...grants];}
function demoMetrics(user){const events=changes.filter(e=>e.actorId===user.id);const created=events.filter(e=>e.action==='created');const expenseEvents=created.filter(e=>e.type==='expenses');const paymentEvents=created.filter(e=>e.type==='receipts');return {students:created.filter(e=>e.type==='students').length,expenses:expenseEvents.length,original:expenseEvents.reduce((n,e)=>n+e.after.paid,0),cash:expenseEvents.reduce((n,e)=>n+(expenses.find(x=>x.id===e.key&&!x.cancelled)?.paid||0),0),payments:paymentEvents.length,edits:events.filter(e=>e.action==='updated').length,cancellations:events.filter(e=>e.action==='cancelled').length};}
function demoAdmin(){return heading('لوحة المدير','أنشئ حساب العامل وحدد ما يراه وما يستطيع تنفيذه.')+`<div class="panel demo-scope-note">هذه تجربة شكلية للحسابات داخل التبويب. الحسابات الفعلية والصلاحيات المحمية تعمل في البرنامج المرتبط بقاعدة البيانات.</div><div class="two-col"><form class="panel" id="demo-user-create"><h2>إنشاء حساب عامل</h2><div class="form-grid body-space"><label>اسم العامل *<input name="name" required maxlength="100"></label><label>اسم المستخدم *<input name="username" required pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}" dir="ltr"></label><label class="field-wide">كلمة المرور *<input name="password" type="password" required minlength="12" maxlength="128" autocomplete="new-password"></label></div><details open><summary>الصلاحيات</summary>${demoGrantFields('new')}</details><p class="muted">التعديل والإلغاء يتطلبان العرض. تسجيل الطالب وحده لا يمنح قبض الدفعات.</p><p class="error" id="demo-user-error" role="alert"></p><button class="primary body-space">إنشاء الحساب</button></form><div class="panel"><h2>الحسابات</h2><div class="body-space">${demoUsers.map(u=>`<div class="managed-row"><div><strong>${esc(u.name)}</strong><p class="muted">${esc(u.username)} · ${u.admin?'مدير':u.active?'مفعل':'معطل'}</p></div>${!u.admin?`<button class="secondary small" data-demo-user="${u.id}">إدارة الحساب</button>`:''}</div>`).join('')}</div></div></div><div class="panel"><h2>نشاط العاملين</h2><label class="body-space">العامل<select id="demo-activity-user">${demoUsers.map(u=>`<option value="${u.id}">${esc(u.name)} · ${esc(u.username)}</option>`).join('')}</select></label><div id="demo-activity-body" class="body-space"></div></div><details><summary>سجل إدارة الحسابات</summary>${demoAccountEvents.slice().reverse().map(e=>`<p>${esc(e.action)} · ${esc(e.name)} · ${esc(e.actor)}</p>`).join('')||'<p class="muted">لا توجد تغييرات بعد.</p>'}</details>`;}
function demoShowMetrics(){const user=demoUsers.find(u=>u.id===$('#demo-activity-user').value),m=demoMetrics(user);$('#demo-activity-body').innerHTML=`<p class="muted">${user.admin?'مدير بجميع الصلاحيات':user.permissions.map(p=>{const [a,b]=p.split('.');return demoAreas[a]+': '+demoActions[b];}).join('، ')||'بلا صلاحيات'}</p><div class="stats">${stat('🎒','طلاب سجلهم',m.students)}${stat('📦','مصروفات سجلها',m.expenses)}${stat('💵','المصروف المسجل أصلاً',money(m.original),'أوقية قديمة')}${stat('💰','صافي تلك المصروفات الآن',money(m.cash),'أوقية قديمة')}${stat('✏️','تعديلات محفوظة',m.edits)}${stat('🕘','إلغاءات محفوظة',m.cancellations)}</div><p class="muted">العدد للأعمال المحفوظة، والصافي بعد التصحيح والإلغاء. عرض الصفحة ليس استهلاكًا يُقاس بنسبة.</p>`;}
function demoBindAdmin(){
 $('#demo-user-create').onsubmit=async e=>{e.preventDefault();const form=e.target,d=new FormData(form),username=d.get('username').trim().toLowerCase();if(demoUsers.some(u=>u.username===username)){$('#demo-user-error').textContent='اسم المستخدم مستخدم.';return;}const salt=crypto.randomUUID(),hash=await demoHash(d.get('password'),salt);const user={id:crypto.randomUUID(),name:d.get('name').trim(),username,hash,salt,admin:false,active:true,permissions:demoNormalizeGrants(d.getAll('grant'))};demoUsers.push(user);demoAccountEvents.push({action:'إنشاء حساب',name:user.name,actor:demoActor.username});render();toast('تم إنشاء حساب العامل داخل المعاينة.');};
 document.querySelectorAll('[data-demo-user]').forEach(b=>b.onclick=()=>demoEditUser(b.dataset.demoUser));
 $('#demo-activity-user').onchange=demoShowMetrics;demoShowMetrics();
}
function demoEditUser(id){const user=demoUsers.find(u=>u.id===id);$('#record-content').innerHTML=`<div class="dialog-head"><h2>حساب ${esc(user.name)}</h2><button class="quiet" id="demo-account-close">✕</button></div><form id="demo-account-edit"><label>اسم العامل<input name="name" value="${esc(user.name)}" required maxlength="100"></label><p class="muted">اسم المستخدم الثابت: ${esc(user.username)}</p><label class="check-row"><input name="active" type="checkbox" ${user.active?'checked':''}>الحساب مفعل</label><label>كلمة مرور جديدة (اختياري)<input name="password" type="password" minlength="12" maxlength="128"></label>${demoGrantFields('edit',user.permissions)}<p class="muted">يبقى نشاط الحساب محفوظًا بعد تعطيله أو تغيير صلاحياته.</p><button class="primary body-space">حفظ الحساب</button></form>`;$('#record-dialog').showModal();$('#demo-account-close').onclick=()=>$('#record-dialog').close();$('#demo-account-edit').onsubmit=async e=>{e.preventDefault();const d=new FormData(e.target);user.name=d.get('name').trim();user.active=d.get('active')==='on';user.permissions=demoNormalizeGrants(d.getAll('grant'));if(d.get('password')){user.salt=crypto.randomUUID();user.hash=await demoHash(d.get('password'),user.salt);}demoAccountEvents.push({action:'تحديث حساب وصلاحيات',name:user.name,actor:demoActor.username});$('#record-dialog').close();render();toast('حُفظ الحساب والصلاحيات.');};}

const demoBaseRender=render;
render=()=>{
 if(!demoActor)return;
 if(!demoMayPage(page))page='dashboard';
 document.querySelectorAll('nav [data-page]').forEach(b=>{b.hidden=!demoMayPage(b.dataset.page);b.classList.toggle('active',b.dataset.page===page);b.setAttribute('aria-current',b.dataset.page===page?'page':'false');});
 if(page==='admin'){$('#crumb').textContent='لوحة المدير';$('#content').innerHTML=demoAdmin();demoBindAdmin();return;}
 if(page==='dashboard'&&!demoActor.admin&&!demoCan('dashboard')){const m=demoMetrics(demoActor);$('#crumb').textContent='الرئيسية';$('#content').innerHTML=heading('أهلًا '+demoActor.name,'اختر العمل المطلوب من القائمة')+`<div class="panel"><p>العمليات المسجلة باسمك</p><div class="stats">${demoCan('students','create')?stat('🎒','طلاب سجلتهم',m.students):''}${demoCan('expenses','create')?stat('📦','مصروفات سجلتها',m.expenses):''}</div></div>`;return;}
 if(page==='students'&&!demoCan('students')&&demoCan('students','create')){profileId=null;studentMode='add';}
 if(page==='payments'&&!demoCan('receipts','create'))financeTab='receipts';
 demoBaseRender();
 if(demoActor.admin)return;
 if(!demoCan('students','create'))$('#add-student')?.remove();
 if(page==='students'){
  if(!demoCan('students'))$('#back-students')?.remove();
  if(!demoCan('students','edit'))$('#edit-child, #profile-edit-child')?.closest('details')?.remove();
  if(!demoCan('receipts')){document.querySelectorAll('#content .stats').forEach(e=>e.remove());$('#profile-pay')?.remove();$('#profile-receipts')?.remove();}
  if(!demoCan('receipts','create'))$('#profile-pay')?.remove();
  const mode=$('#fee-mode');if(mode){[...mode.options].filter(o=>o.value==='exempt'||(o.value==='pay'&&!demoCan('receipts','create'))).forEach(o=>o.remove());}
 }
 if(page==='payments'&&!demoCan('receipts','create'))document.querySelector('[data-finance="payment"]')?.remove();
 if(page==='expenses'){
  if(!demoCan('expenses','create'))$('#expense-form')?.remove();
  if(!demoCan('expenses')){document.querySelector('#content .two-col > div.panel')?.remove();document.querySelectorAll('#content .managed-row').forEach(e=>e.closest('.panel')?.remove());}
 }
 if(page==='registration'){
  if(!demoCan('departments','create'))$('#department-form')?.closest('.panel')?.remove();
  if(!demoCan('departments','edit'))$('#transfer-form')?.remove();
  if(!demoCan('departments'))document.querySelector('#content .table-wrap')?.closest('.panel')?.remove();
 }
};
