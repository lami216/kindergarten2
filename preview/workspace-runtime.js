/* Pages only. Disposable synthetic state; never a production API or ledger. */
'use strict';
window.LIVE_APP=true;
const previewNativeFetch=window.fetch.bind(window);
const previewConfig=previewNativeFetch('workspace-config.json'+new URL(document.currentScript.src).search).then(r=>{if(!r.ok)throw Error('تعذر تحميل المعاينة.');return r.json();});
const previewClone=x=>JSON.parse(JSON.stringify(x));
const previewState={students:previewClone(students).map(s=>({...s,id:String(s.id),parent_id:'P'+s.id,pickups:[],health:'',allergy:'',notes:'',place:'',address:'',revision:'1',parent_revision:'1',account_revision:'1',ledger_revision:1,monthlyOwed:s.exempt?0:3000,waivedRegistration:0,waivedGilet:0,waivedMonthly:0,photo:{revision:0,data:null},start:today})),receipts:previewClone(receipts).map(r=>({...r,student:String(r.student),revision:1,cancelled:false})),expenses:previewClone(expenses).map((e,i)=>({...e,id:i+1,revision:'1',cancelled:false,notes:'',payment_method:'كاش'})),departments:departments.map((name,i)=>({id:i+1,name,revision:'1',cancelled:false})),changes:[],users:[{user_id:'owner',username:'owner',employee_name:'صاحب الروضة',is_admin:true,active:true,permissions:[],auth_version:1}],prices:{registration:1000,gilet:2000,tuition:3000},feeRevision:'1',tables:{},requests:new Map(),principal:null,sequence:200};
previewState.students.push({...previewClone(previewState.students[0]),id:'archived-1',name:'طالب مؤرشف للمراجعة',parent_id:'PA',parent:'ولي طالب مؤرشف',fatherName:'ولي طالب مؤرشف',phone:'00000999',fatherPhone:'00000999',class:'',registration:1000,gilet:2000,cancelled:true,paused:true});
previewState.receipts.push({id:106,student:'archived-1',amount:1500,registration:1000,gilet:500,monthly:0,date:today,cancelled:false,revision:1});
const previewPasswords=new Map();
const previewCan=p=>!!previewState.principal&&(previewState.principal.is_admin||previewState.principal.permissions.includes(p));
function previewRequire(p){if(!previewCan(p))throw Error('ليس لديك صلاحية لهذا الإجراء في حساب المعاينة.');}
function previewStudent(id){const s=previewState.students.find(s=>s.id===String(id));if(!s)throw Error('الطالب غير موجود.');return s;}
function previewAmount(x,zero=false){const n=Number(x);if(!Number.isFinite(n)||n<0||(!zero&&!n)||!Number.isInteger(n))throw Error('أدخل مبلغًا صحيحًا.');return n;}
function previewRevision(row,expected){if(String(row.revision)!==String(expected))throw Error('تغيّر السجل؛ أعد فتحه قبل الحفظ.');}
function previewBump(s){s.revision=String(Number(s.revision)+1);s.account_revision=String(Number(s.account_revision)+1);s.ledger_revision++;}
function previewAudit(type,key,action,before,after,reason){previewState.changes.push({id:++previewState.sequence,type,key,action,before:previewClone(before),after:previewClone(after),reason:reason||'إجراء من المعاينة',actor:previewState.principal.username,actorId:previewState.principal.user_id,time:new Date().toISOString()});}
function previewAccount(s){
 const rs=previewState.receipts.filter(r=>r.student===s.id&&!r.cancelled),sum=k=>rs.reduce((n,r)=>n+Number(r[k]||0),0);
 const registration_due=Math.max(0,s.registration-sum('registration')-s.waivedRegistration),gilet_due=Math.max(0,s.gilet-sum('gilet')-s.waivedGilet);
 return {paid:sum('amount'),due:registration_due+gilet_due+Math.max(0,s.monthlyOwed-sum('monthly')-s.waivedMonthly),full:Math.floor(sum('monthly')/3000),monthPaid:sum('monthly'),registration_due,gilet_due};
}
function previewOverview(){
 const rs=previewState.receipts.filter(r=>!r.cancelled),sum=k=>rs.reduce((n,r)=>n+Number(r[k]||0),0),cash=table=>(previewState.tables[table]||[]).reduce((n,r)=>n+Number(r.cash||0),0);
 const operational=previewState.expenses.filter(e=>!e.cancelled).reduce((n,e)=>n+e.paid,0),salary=cash('teacher_payments'),advance=cash('teacher_advances');
 return {students_count:previewState.students.filter(s=>!s.cancelled).length,archived_students:previewState.students.filter(s=>s.cancelled).length,total_cash:sum('amount'),new_cash:sum('amount'),registration_cash:sum('registration'),gilet_cash:sum('gilet'),monthly_cash:sum('monthly'),operational_cash:operational,salary_cash:salary,advance_cash:advance,expenses:operational+salary+advance,remaining_cash:sum('amount')-operational-salary-advance,due_now:previewState.students.reduce((n,s)=>n+previewAccount(s).due,0),registration_children:previewState.students.filter(s=>s.registration>0&&rs.filter(r=>r.student===s.id).reduce((n,r)=>n+r.registration,0)>=s.registration).length,gilet_count:previewState.students.filter(s=>s.gilet>0&&rs.filter(r=>r.student===s.id).reduce((n,r)=>n+r.gilet,0)>=s.gilet).length,prepaid_cash:0};
}
async function previewSnapshot(){
 const config=await previewConfig,can=previewCan,ss=previewState.students.map(s=>({...previewClone(s),account:previewAccount(s)}));
 const visible=can('students.view')||can('payments.view')||can('departments.view');
 return {...config,today,students:visible?ss:[],receipts:can('payments.view')?previewClone(previewState.receipts):[],expenses:can('expenses.view')?previewClone(previewState.expenses):[],departments:can('departments.view')?previewClone(previewState.departments):[],changes:can('history.view')?previewClone(previewState.changes):[],prices:previewClone(previewState.prices),overview:can('reports.view')?previewOverview():null,users:previewState.principal.is_admin?previewClone(previewState.users):[],account_events:[],metrics:{},families:can('students.view')?ss.filter(s=>!s.cancelled).map(s=>({id:s.parent_id,father:s.fatherName,fatherPhone:s.fatherPhone,mother:s.motherName,motherPhone:s.motherPhone})):[],tools:config.tools.filter(t=>can(previewResource(t.key)+'.view')).map(t=>({...t,edit:can(previewResource(t.key)+'.edit'),delete:can(previewResource(t.key)+'.delete'),create:t.create&&can(previewResource(t.key)+'.create')}))};
}
function previewResource(t){return {teacher_payments:'salaries',teacher_advances:'salaries',monthly_accounts:'accounts',monthly_waivers:'accounts',academic_years:'years',registrations:'accounts'}[t]||t;}
function previewTable(table){
 if(table==='parents')return previewState.students.map(s=>({id:s.parent_id,title:s.parent,revision:s.parent_revision,cancelled:false,values:{father_name:s.fatherName,father_mobile:s.fatherPhone,mother_name:s.motherName,mother_mobile:s.motherPhone}}));
 if(table==='monthly_accounts')return previewState.students.map(s=>({id:s.id,title:s.name,revision:s.account_revision,cancelled:!!s.cancelled,values:{start_date:s.start,status:s.exempt?'exempt':'regular'}}));
 return previewState.tables[table]||(previewState.tables[table]=[]);
}
function previewIssue(s,amount,kind=null,date=today,corrects_id=null){
 const a=previewAccount(s);let registration=kind==='gilet'?0:Math.min(amount,a.registration_due),gilet=kind==='registration'?0:Math.min(amount-registration,a.gilet_due);
 if(kind==='registration')registration=amount;if(kind==='gilet')gilet=amount;
 const r={id:++previewState.sequence,student:s.id,amount,registration,gilet,monthly:amount-registration-gilet,date,cancelled:false,corrects_id,revision:++s.ledger_revision};previewState.receipts.push(r);previewBump(s);previewAudit('monthly_receipts',r.id,'created',null,r,'دفعة في المعاينة');return r;
}
async function previewOperation(op,d={}){
 if(op==='login'){
  const u=d.username?previewState.users.find(u=>u.username===d.username&&u.active):previewState.users[0];
  if(!u||(d.username&&previewPasswords.get(u.user_id)!==d.password))throw Error('تعذر الدخول بحساب المعاينة هذا.');previewState.principal=u;return {ok:true};
 }
 if(!previewState.principal)throw Error('افتح المعاينة أولًا.');
 if(op==='session')return {user:previewClone(previewState.principal),csrf:'synthetic-pages-only',management:false};
 if(op==='logout'){previewState.principal=null;return {ok:true};}
 if(op==='snapshot')return previewSnapshot();
 if(op==='fees.read'){previewRequire('fees.view');return {values:previewClone(previewState.prices),revision:previewState.feeRevision};}
 if(op==='teachers.options'){previewRequire('salaries.view');return previewTable('teachers').map(r=>({id:r.id,name:r.values.full_name,identity:r.values.national_id,salary:Number(r.values.salary),archived:r.cancelled}));}
 const permissions={'students.create':'students.create','students.edit':'students.edit','students.restore':'students.edit','students.waive':'accounts.delete','photos.save':'students.edit','departments.create':'departments.create','departments.transfer':'departments.edit','expenses.create':'expenses.create','expenses.settle':'expenses.edit','payments.preview':'payments.create','payments.create':'payments.create','fees.collect':'payments.create','fees.save':'fees.edit','payroll.save':'salaries.create','accounts.setup':'accounts.edit','reports.read':'reports.view','reports.export':'reports.view'};
 if(permissions[op])previewRequire(permissions[op]);
 if(d.request_token&&previewState.requests.has(d.request_token))return previewClone(previewState.requests.get(d.request_token));
 let result={ok:true};
 if(op==='students.create'){
  if(!d.name||!(d.father&&d.fatherPhone||d.mother&&d.motherPhone))throw Error('أدخل اسم الطفل واسم وهاتف أحد الوالدين.');
  if(d.birth>today)throw Error('تاريخ الميلاد لا يكون مستقبليًا.');
  const exempt=d.mode==='exempt',registration=exempt?0:d.registration?previewState.prices.registration:0,gilet=exempt?0:d.gilet?previewState.prices.gilet:0,cash=exempt?0:previewAmount(d.amount||0,true);
  if(cash&&cash<registration+gilet)throw Error('المبلغ لا يغطي الرسوم المختارة.');
  const id='PAGES'+(++previewState.sequence),parent=d.existing_parent_id?previewState.students.find(s=>s.parent_id===d.existing_parent_id):null;
  const s={id,name:d.name,birth:d.birth,gender:d.gender,class:'',parent_id:parent?.parent_id||'F'+id,parent:parent?.parent||d.father||d.mother,phone:parent?.phone||d.fatherPhone||d.motherPhone,fatherName:parent?.fatherName||d.father||'',fatherPhone:parent?.fatherPhone||d.fatherPhone||'',motherName:parent?.motherName||d.mother||'',motherPhone:parent?.motherPhone||d.motherPhone||'',place:d.place||'',address:d.address||'',health:d.health||'',allergy:'',notes:'',pickups:[],registration,gilet,exempt,start:today,monthlyOwed:0,waivedRegistration:0,waivedGilet:0,waivedMonthly:0,revision:'1',account_revision:'1',parent_revision:'1',ledger_revision:1,photo:{revision:d.photo?1:0,data:d.photo?'data:image/'+(d.photo.startsWith('/9j')?'jpeg':'png')+';base64,'+d.photo:null},cancelled:false};
  previewState.students.push(s);if(cash)previewIssue(s,cash);previewAudit('students',id,'created',null,s,'تسجيل طفل');result={id,created:true};
 }else if(op==='students.restore'){
  const s=previewStudent(d.student);previewRevision(s,d.revision);if(!s.cancelled)throw Error('الملف مسترجع بالفعل.');s.cancelled=false;s.paused=true;previewBump(s);previewAudit('students',s.id,'updated',{cancelled:true},s,d.reason);
 }else if(op==='students.waive'){
  const s=previewStudent(d.student),a=previewAccount(s);if(s.cancelled||s.ledger_revision!==d.revision||a.due!==Number(d.due))throw Error('تغيّر الحساب؛ أعد فتح نافذة إسقاط الدين.');
  s.waivedRegistration+=a.registration_due;s.waivedGilet+=a.gilet_due;s.waivedMonthly+=a.due-a.registration_due-a.gilet_due;previewBump(s);previewAudit('monthly_waivers',s.id,'created',null,{name:s.name,amount:a.due},d.reason);result={waived:a.due,created:true};
 }else if(op==='students.edit'){
  const s=previewStudent(d.id);previewRevision(s,d.revision);if(s.cancelled)throw Error('الملف مؤرشف.');const before=previewClone(s);for(const k of ['name','birth','gender','place','address','health','allergy','notes','pickups'])if(k in d.values)s[k]=d.values[k];previewBump(s);previewAudit('students',s.id,'updated',before,s,d.reason);result={id:s.id};
 }else if(op==='photos.save'){
  const s=previewStudent(d.student);if(s.photo.revision!==d.revision)throw Error('تغيّرت الصورة؛ أعد فتحها.');s.photo={revision:d.revision+1,data:d.remove?null:'data:image/'+(d.photo.startsWith('/9j')?'jpeg':'png')+';base64,'+d.photo};previewAudit('student_photos',s.id,d.remove?'deleted':'updated',null,{name:s.name,photo:d.remove?'بلا صورة':'صورة محفوظة'},d.reason);
 }else if(op==='departments.create'){
  if(previewState.departments.some(x=>!x.cancelled&&x.name===d.name))throw Error('اسم القسم موجود.');const r={id:++previewState.sequence,name:d.name,revision:'1',cancelled:false};previewState.departments.push(r);previewAudit('school_departments',r.id,'created',null,r);result={id:r.id};
 }else if(op==='departments.transfer'){
  const dep=previewState.departments.find(x=>x.id===d.department_id&&!x.cancelled);if(!dep)throw Error('القسم غير متاح.');for(const id of d.ids){const s=previewStudent(id);if(s.cancelled)throw Error('الطفل مؤرشف.');const old=s.class;s.class=dep.name;previewBump(s);previewAudit('student_departments',id,'updated',{class:old},{name:s.name,class:s.class},'نقل بين الأقسام');}
 }else if(op==='payments.preview'){
  const s=previewStudent(d.student);if(s.cancelled||s.exempt)throw Error('الحساب مؤرشف أو معفي؛ لا يقبل دفعة جديدة.');result={amount:previewAmount(d.amount),revision:s.ledger_revision,tariff:previewState.prices.tuition,months:[{start:today,end:today,allocating:Number(d.amount)}]};
 }else if(op==='payments.create'||op==='fees.collect'){
  const s=previewStudent(d.student);if(s.cancelled||s.exempt)throw Error('الحساب مؤرشف أو معفي.');if(op==='payments.create'&&(d.revision!==s.ledger_revision||d.tariff!==previewState.prices.tuition))throw Error('تغيّر الحساب؛ أعد المعاينة.');const amount=op==='fees.collect'?previewAccount(s)[d.kind+'_due']:previewAmount(d.amount);const r=previewIssue(s,amount,d.kind||null);result={id:r.id,created:true};
 }else if(op==='expenses.create'){
  const amount=previewAmount(d.amount),paid=previewAmount(d.paid,true);if(paid>amount)throw Error('المدفوع أكبر من إجمالي المصروف.');const e={...d,id:++previewState.sequence,amount,paid,revision:'1',cancelled:false,notes:d.notes||''};previewState.expenses.push(e);previewAudit('expenses',e.id,'created',null,e);result={id:e.id,created:true};
 }else if(op==='expenses.settle'){
  const e=previewState.expenses.find(e=>e.id===d.id);previewRevision(e,d.revision);const paid=previewAmount(d.amount);if(paid>e.amount-e.paid)throw Error('المبلغ أكبر من المتبقي.');const before=previewClone(e);e.paid+=paid;e.revision=String(Number(e.revision)+1);previewAudit('expenses',e.id,'updated',before,e,d.reason);
 }else if(op==='records.change'){
  const resource={receipts:'payments',students:'students',expenses:'expenses',departments:'departments'}[d.type];if(!resource)throw Error('السجل غير متاح.');previewRequire(resource+'.'+(d.mode==='cancel'?'delete':'edit'));
  const rows=d.type==='students'?previewState.students:d.type==='receipts'?previewState.receipts:d.type==='expenses'?previewState.expenses:previewState.departments,r=rows.find(r=>String(r.id)===String(d.id));if(!r)throw Error('السجل غير موجود.');
  const before=previewClone(r),v=d.values||{};if(d.type!=='receipts')previewRevision(r,d.revision);else if(previewStudent(r.student).ledger_revision!==d.revision)throw Error('تغيّر الحساب.');
  if(d.mode==='cancel'){
   if(d.type==='students'&&previewAccount(r).due)throw Error('أسقط أو سدّد الدين المستحق قبل الأرشفة.');
   if(d.type==='departments')for(const s of previewState.students.filter(s=>s.class===r.name)){s.class=previewState.departments.find(x=>x.id===d.destination)?.name||'';previewBump(s);}
   r.cancelled=true;if(d.type==='expenses'){r.amount=0;r.paid=0;}if(d.type==='receipts')previewBump(previewStudent(r.student));
  }else if(d.type==='expenses'){
   const amount=previewAmount(v.amount),paid=previewAmount(v.paid,true);if(paid>amount)throw Error('المدفوع أكبر من إجمالي المصروف؛ صحح أحد المبلغين.');Object.assign(r,{amount,paid,category:v.category,date:v.date,payee:v.payee});
  }else if(d.type==='departments'){for(const s of previewState.students.filter(s=>s.class===r.name))s.class=v.name;r.name=v.name;}
  else if(d.type==='receipts'){r.cancelled=true;const replacement=previewIssue(previewStudent(r.student),previewAmount(v.amount),null,v.date,r.id);result={id:replacement.id,created:true};}
  else return previewOperation('students.edit',d);
  r.revision=String(Number(r.revision)+1);previewAudit(d.type,r.id,d.mode==='cancel'?'archived':'updated',before,r,d.reason);if(!result.id)result={id:r.id,cancelled:d.mode==='cancel'};
 }else if(op==='fees.save'){
  if(d.revision!==previewState.feeRevision)throw Error('تغيّرت الرسوم.');previewState.prices={registration:previewAmount(d.registration,true),gilet:previewAmount(d.gilet,true),tuition:previewAmount(d.tuition)};previewState.feeRevision=String(Number(previewState.feeRevision)+1);previewAudit('monthly_tariffs','1','updated',null,previewState.prices,d.reason);
 }else if(op==='tools.list'){
  const config=(await previewConfig).tools.find(t=>t.key===d.table);if(!config)throw Error('القائمة غير متاحة.');previewRequire(previewResource(d.table)+'.view');const rs=previewTable(d.table).filter(r=>(d.archived||!r.cancelled)&&searchText(JSON.stringify(r)).includes(searchText(d.query))),page=d.page||1;return {items:previewClone(rs.slice((page-1)*20,page*20)),page,pages:Math.max(1,Math.ceil(rs.length/20)),total:rs.length};
 }else if(op==='tools.change'){
  const table=d.table,config=(await previewConfig).tools.find(t=>t.key===table);if(!config)throw Error('السجل غير متاح.');previewRequire(previewResource(table)+'.'+(d.mode==='create'?'create':d.mode==='edit'?'edit':'delete'));
  if(table==='parents'){
   const parent=previewTable(table).find(r=>r.id===d.id);if(!parent)throw Error('ولي الأمر غير موجود.');previewRevision(parent,d.revision);if(d.mode==='cancel')throw Error('ولي الأمر مرتبط بملف طالب؛ تبقى بياناته محفوظة.');for(const s of previewState.students.filter(s=>s.parent_id===d.id)){Object.assign(s,{fatherName:d.values.father_name,fatherPhone:d.values.father_mobile,motherName:d.values.mother_name,motherPhone:d.values.mother_mobile});s.parent=s.fatherName||s.motherName;s.phone=s.fatherPhone||s.motherPhone;s.parent_revision=String(Number(s.parent_revision)+1);}previewAudit(table,d.id,'updated',parent.values,d.values,d.reason);
  }else if(table==='monthly_accounts'){
   const s=previewStudent(d.id);if(s.account_revision!==d.revision)throw Error('تغيّر الاشتراك.');if(d.mode==='cancel'&&previewAccount(s).due)throw Error('أسقط أو سدّد الدين أولًا.');if(d.mode==='cancel')s.paused=true;else{s.start=d.values.start_date;s.exempt=d.values.status==='exempt';}previewBump(s);previewAudit(table,s.id,'updated',null,d.values,d.reason);
  }else{
   const rs=previewTable(table);let r=rs.find(x=>String(x.id)===String(d.id));const before=r?previewClone(r):null;
   if(d.mode==='create'){r={id:'T'+(++previewState.sequence),title:d.values.full_name||d.values.item_name,revision:'1',values:previewClone(d.values),cancelled:false};rs.push(r);}
   else{if(!r)throw Error('السجل غير موجود.');previewRevision(r,d.revision);if(d.mode==='void_document')r.document='cancelled';else if(d.mode==='cancel'){r.cancelled=true;r.cash=0;}else{r.values=previewClone(d.values);r.title=r.values.full_name||r.values.item_name||r.title;if(table==='teacher_payments')r.cash=Number(r.values.base_salary)+Number(r.values.bonus)-Number(r.values.deductions);if(table==='teacher_advances')r.cash=Number(r.values.amount);}r.revision=String(Number(r.revision)+1);}
   previewAudit(table,r.id,d.mode==='create'?'created':d.mode==='cancel'?'archived':'updated',before,r,d.reason);result={id:r.id};
  }
 }else if(op==='payroll.save'){
  const t=previewTable('teachers').find(t=>t.id===d.teacher&&!t.cancelled);if(!t)throw Error('اختر المعلمة.');const cash=previewAmount(d.kind==='advance'?d.amount:Number(d.base)+Number(d.bonus)-Number(d.deductions));const table=d.kind==='advance'?'teacher_advances':'teacher_payments',r={id:++previewState.sequence,title:t.title,teacher:t.id,cash,document:'active',cancelled:false,revision:'1',values:{salary_month:d.month,payment_date:d.date,advance_date:d.date,base_salary:Number(d.base)||0,bonus:Number(d.bonus)||0,deductions:Number(d.deductions)||0,amount:cash,notes:d.notes}};previewTable(table).push(r);previewAudit(table,r.id,'created',null,r);result={id:r.id,created:true};
 }else if(op==='reports.read'){
  if(d.start>d.end||d.end>today)throw Error('راجع الفترة.');if(d.kind==='finance')return {summary:previewOverview(),items:[]};const perm={students:'students',debt:'payments',expenses:'expenses',salaries:'salaries'}[d.kind];previewRequire(perm+'.view');return {summary:{},items:d.kind==='students'?previewState.students.filter(s=>!s.cancelled).map(s=>({'الطالب':s.name,'القسم':s.class,'ولي الأمر':s.parent,'الهاتف':s.phone})):d.kind==='debt'?previewState.students.filter(s=>previewAccount(s).due).map(s=>({'الطالب':s.name,'المتبقي':previewAccount(s).due,'الحالة':s.cancelled?'مؤرشف':'نشط'})):d.kind==='expenses'?previewState.expenses.filter(e=>!e.cancelled).map(e=>({'المصروف':e.category,'الإجمالي':e.amount,'المدفوع':e.paid})):previewTable('teacher_payments').filter(r=>!d.teacher||d.teacher===r.teacher).map(r=>({'المعلمة':r.title,'النقد':r.cash,'الشهر':r.values.salary_month}))};
 }else if(op==='users.save'){
  if(!previewState.principal.is_admin)throw Error('للمدير فقط.');let u=previewState.users.find(u=>u.user_id===d.id);if(u&&u.auth_version!==d.version)throw Error('تغيّر الحساب.');if(!u){u={user_id:'U'+(++previewState.sequence),username:d.username,is_admin:false,auth_version:0};previewState.users.push(u);}const grants=new Set(d.permissions);for(const p of [...grants]){const [area,action]=p.split('.');if(['edit','delete','create'].includes(action)&&area!=='students'&&area!=='expenses'||['edit','delete'].includes(action))grants.add(area+'.view');if(area==='accounts'&&['edit','delete'].includes(action))grants.add('payments.view');}Object.assign(u,{employee_name:d.name,active:d.active,permissions:[...grants],auth_version:u.auth_version+1});if(d.password)previewPasswords.set(u.user_id,d.password);result={id:u.user_id};
 }else if(op==='accounts.setup'){
  const s=previewStudent(d.student);s.start=d.start;s.exempt=d.status==='exempt';previewBump(s);
 }else throw Error('هذا الإجراء متاح على الخادم الفعلي. المعاينة على Pages لا تتصل ببيانات الروضة.');
 if(d.request_token)previewState.requests.set(d.request_token,previewClone(result));return result;
}
window.fetch=async function(input,init={}){
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return previewNativeFetch(input,init);
 const op=url.pathname.slice(5);try{return new Response(JSON.stringify(await previewOperation(op,init.body?JSON.parse(init.body):{})),{status:200,headers:{'Content-Type':'application/json'}});}catch(error){return new Response(JSON.stringify({error:error.message}),{status:!previewState.principal&&op!=='login'?401:422,headers:{'Content-Type':'application/json'}});}
};
