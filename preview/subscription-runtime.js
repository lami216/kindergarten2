/* Disposable adapter for intake dates and audited in-file corrections. */
'use strict';
const beforeDatedAccount=previewAccount;
previewAccount=function(s){
 if(s.dateTracked){let count=0;while(count<1200&&previewAnniversary(s.start,count+1)<=today)count++;s.monthlyOwed=s.exempt?Number(s.monthlyOwed||0):count*previewState.prices.tuition;}
 const a=beforeDatedAccount(s),price=previewState.prices.tuition,paid=a.monthPaid,full=Math.floor(paid/price),settled=paid+Number(s.waivedMonthly||0),index=Math.floor(settled/price);
 const end=full?new Date(previewAnniversary(s.start,full)+'T12:00:00Z'):null;if(end)end.setUTCDate(end.getUTCDate()-1);
 const active=!s.exempt&&!s.cancelled&&!s.paused,remaining=price-settled%price,partial=Math.max(0,paid-index*price);
 const rs=previewState.receipts.filter(r=>r.student===s.id&&!r.cancelled),fee_details={};
 for(const key of ['registration','gilet'])if(s[key]){const received=rs.reduce((n,r)=>n+Number(r[key]||0),0),waived=Number(s[key==='gilet'?'waivedGilet':'waivedRegistration']||0);fee_details[key]={price:s[key],paid:received,waived,remaining:Math.max(0,s[key]-received-waived)};}
 return {...a,full,paid_through:end?.toISOString().slice(0,10)||null,next_unpaid:active?previewAnniversary(s.start,index):null,next_due:active?previewAnniversary(s.start,index+1):null,partial_period:active&&partial?{start:previewAnniversary(s.start,index),end:previewAnniversary(s.start,index+1),paid:partial,remaining}:null,fee_details};
};
const beforeSubscriptionOperation=previewOperation;
const beforeDatedSnapshot=previewSnapshot;
previewSnapshot=async function(){
 const result=await beforeDatedSnapshot();
 for(const receipt of result.receipts)receipt.revision=previewStudent(receipt.student).ledger_revision;
 for(const row of result.students){
  const s=previewStudent(row.id);
  if(previewCan('students.view')&&previewCan('students.edit')&&previewCan('accounts.edit')&&!s.cancelled&&!s.noAccount)
   row.subscription_edit={start:s.start,revision:s.account_revision,ledger_revision:s.ledger_revision};
  if(!previewCan('payments.view')){row.account=null;delete row.start;}
 }
 return result;
};
function previewIntakeDate(value,birth){
 const date=new Date(value+'T12:00:00Z');
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value)||Number.isNaN(+date)||date.toISOString().slice(0,10)!==value||value<'1990-01-01'||value>today||birth&&value<birth)
  throw Error(I18N.tr('subscription.invalidStart'));
}
previewOperation=async function(op,d={}){
 if(op==='students.create'&&d.start_date!==undefined)previewIntakeDate(d.start_date,d.birth);
 let correction=null;
 if(op==='students.edit'&&d.values?.start_date!==undefined){
  previewRequire('students.edit');previewRequire('accounts.edit');
  const s=previewStudent(d.id);previewRevision(s,d.revision);
  if(String(d.account_revision)!==String(s.account_revision)||d.ledger_revision!==s.ledger_revision)throw Error(I18N.tr('subscription.staleEdit'));
  previewIntakeDate(d.values.start_date,d.values.birth??s.birth);
  if(s.departure&&d.values.start_date>s.departure)throw Error(I18N.tr('subscription.afterDeparture'));
  if(d.values.start_date!==s.start)correction={student:s,before:{start_date:s.start},start:d.values.start_date};
 }
 const result=await beforeSubscriptionOperation(op,d);
 if(op==='students.create'){const s=previewStudent(result.id);s.start=d.start_date||today;s.registered_on=s.start;s.start_selected=d.start_date!==undefined;s.dateTracked=true;}
 if(correction){const s=correction.student;s.start=s.registered_on=correction.start;s.start_selected=true;s.dateTracked=true;previewAudit('monthly_accounts',s.id,'updated',correction.before,{start_date:s.start},d.reason);}
 return result;
};
