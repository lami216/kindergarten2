/* Disposable preview only. Production reads its PostgreSQL cash-event ledger. */
'use strict';
const previewCashEvents=new Map(previewState.expenses.map(e=>[e.id,[{date:e.date,amount:Number(e.paid),kind:'initial'}]]));
const beforeFinanceOperation=previewOperation;
previewOperation=async function(op,d={}){
 if(op==='reports.finance'){previewRequire('reports.view');return previewFinance(d);}
 const expense=op==='expenses.settle'||op==='records.change'&&d.type==='expenses'?previewState.expenses.find(e=>String(e.id)===String(d.id)):null;
 const old=expense?previewClone(expense):null;
 const result=await beforeFinanceOperation(op,d);
 if(op==='expenses.create'){const e=previewState.expenses.find(e=>e.id===result.id);previewCashEvents.set(e.id,[{date:e.date,amount:Number(e.paid),kind:'initial'}]);}
 if(expense){const events=previewCashEvents.get(expense.id)||[];if(op==='expenses.settle')events.push({date:d.date,amount:expense.paid-old.paid,kind:'settlement'});else if(d.mode==='cancel')events.forEach(e=>e.amount=0);else if(d.mode==='edit'){const delta=expense.paid-old.paid;if(delta){let initial=events.find(e=>e.kind==='initial');if(!initial){initial={date:old.date,amount:0,kind:'initial'};events.unshift(initial);}initial.amount+=delta;}}previewCashEvents.set(expense.id,events);}
 return result;
};
async function previewFinance(d){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(d.start)||!/^\d{4}-\d{2}-\d{2}$/.test(d.end)||d.start>d.end||d.end>today)throw Error(I18N.sourceLabel('راجع تاريخ البداية والنهاية.'));
 const all=[];
 for(const r of previewState.receipts.filter(r=>!r.cancelled)){
  const s=previewState.students.find(s=>s.id===r.student);
  all.push({key:'receipt:'+r.id,date:r.date,category:'income',amount:r.amount,label:s?.name||'',party:s?.parent||'',source_id:r.id,student_id:r.student,registration:r.registration||0,gilet:r.gilet||0,monthly:r.monthly||0,prepaid:0,void_document:false});
 }
 for(const e of previewState.expenses)for(const [i,event]of(previewCashEvents.get(e.id)||[]).entries())if(event.amount)all.push({key:'expense:'+e.id+':'+i,date:event.date,category:'operational',amount:event.amount,label:e.category,party:e.payee||'',source_id:e.id,student_id:null,registration:0,gilet:0,monthly:0,prepaid:0,void_document:false});
 for(const [table,category,field]of[['teacher_payments','salary','payment_date'],['teacher_advances','advance','advance_date']])for(const r of previewTable(table))if(r.cash)all.push({key:category+':'+r.id,date:r.values[field],category,amount:r.cash,label:r.title,party:r.values.salary_month,source_id:r.id,student_id:null,registration:0,gilet:0,monthly:0,prepaid:0,void_document:r.document==='cancelled'});
 const permissions=Object.fromEntries(['payments','expenses','salaries','students'].map(k=>[k,previewCan(k+'.view')]));
 const opening=all.filter(r=>r.date<d.start).reduce((n,r)=>n+(r.category==='income'?r.amount:-r.amount),0);
 const items=all.filter(r=>r.amount>0&&r.date>=d.start&&r.date<=d.end).sort((a,b)=>b.date.localeCompare(a.date)||b.key.localeCompare(a.key)).map((r,n)=>permissions[{income:'payments',operational:'expenses',salary:'salaries',advance:'salaries'}[r.category]]?r:{...r,key:'restricted:'+n,label:'',party:'',source_id:null,student_id:null});
 const summary={};for(const key of ['income','operational','salary','advance'])summary[key]=items.filter(r=>r.category===key).reduce((n,r)=>n+r.amount,0);
 summary.outgoing=summary.operational+summary.salary+summary.advance;summary.net=summary.income-summary.outgoing;summary.opening=opening;summary.closing=opening+summary.net;
 for(const key of ['registration','gilet','monthly','prepaid'])summary[key]=items.filter(r=>r.category==='income').reduce((n,r)=>n+r[key],0);
 summary.other_income=summary.income-summary.registration-summary.gilet-summary.monthly;
 const students=previewState.students.filter(s=>s.start<=d.end).map(s=>{const rs=previewState.receipts.filter(r=>r.student===s.id&&!r.cancelled&&r.date<=d.end),sum=k=>rs.reduce((n,r)=>n+Number(r[k]||0),0);return {id:s.id,name:s.name,archived:s.cancelled,amount:Math.max(0,s.registration-sum('registration')-s.waivedRegistration)+Math.max(0,s.gilet-sum('gilet')-s.waivedGilet)+Math.max(0,s.monthlyOwed-sum('monthly')-s.waivedMonthly)};}).filter(s=>s.amount);
 const suppliers=previewState.expenses.filter(e=>!e.cancelled&&e.date<=d.end).map(e=>({id:e.id,name:e.category,payee:e.payee,amount:Math.max(0,e.amount-(previewCashEvents.get(e.id)||[]).filter(x=>x.date<=d.end).reduce((n,x)=>n+x.amount,0))})).filter(e=>e.amount);
 const debt={students_total:students.reduce((n,s)=>n+s.amount,0),suppliers_total:suppliers.reduce((n,s)=>n+s.amount,0),students:permissions.payments?students:[],suppliers:permissions.expenses?suppliers:[]};
 const result={start:d.start,end:d.end,summary,items,permissions,debt};
 result.revision=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(result))))).map(n=>n.toString(16).padStart(2,'0')).join('');result.generated_at=new Date().toISOString();return result;
}
// Minimal genuine XLSX, with text cells stored as inline strings (never formulas).
function previewReportWorkbook(report,d){
 const t=k=>I18N.tr(`reports.${k}`),escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
 const q=(d.query||'').trim().normalize('NFKC').toLowerCase(),category=d.category||'all';
 const rows=report.items.filter(r=>(category==='all'||r.category===category||category==='outgoing'&&r.category!=='income')&&[r.label,r.party,r.source_id,r.date].map(v=>String(v??'')).join(' ').normalize('NFKC').toLowerCase().includes(q));
 const summary=[[t('title'),report.start,report.end],[t('generated'),report.generated_at],[t('query'),d.query||'',t(category)],...['income','outgoing','net','opening','closing','registration','gilet','monthly','prepaid','other_income','operational','salary','advance'].map(k=>[t(k),report.summary[k]]),[t('studentsDebt'),report.debt.students_total],[t('suppliersDebt'),report.debt.suppliers_total],[t('filteredTotal'),rows.reduce((n,r)=>n+(r.category==='income'?r.amount:-r.amount),0)],[t('cashNote')]];
 const detail=[['date','type','description','party','incomingColumn','outgoingColumn','reference'].map(t),...rows.map(r=>[r.date,t(r.category+'Entry'),r.label,r.party,r.category==='income'?r.amount:0,r.category!=='income'?r.amount:0,r.source_id])];
 const debts=[[t('asOf'),report.end],['type','description','amount'].map(t),...['students','suppliers'].flatMap(k=>report.debt[k].map(r=>[t(k==='students'?'studentsDebt':'suppliersDebt'),r.name,r.amount]))];
 const sheets=[summary,detail,debts],names=['summarySheet','detailsSheet','debtSheet'].map(t),enc=new TextEncoder();
 const xmlHead='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
 const files=[['[Content_Types].xml',xmlHead+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+sheets.map((_,i)=>`<Override PartName="/xl/worksheets/sheet${i+1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')+'</Types>'],['_rels/.rels',xmlHead+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],['xl/workbook.xml',xmlHead+'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+names.map((name,i)=>`<sheet name="${escape(name)}" sheetId="${i+1}" r:id="rId${i+1}"/>`).join('')+'</sheets></workbook>'],['xl/_rels/workbook.xml.rels',xmlHead+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+sheets.map((_,i)=>`<Relationship Id="rId${i+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i+1}.xml"/>`).join('')+'</Relationships>']];
 sheets.forEach((rows,i)=>files.push([`xl/worksheets/sheet${i+1}.xml`,xmlHead+'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0" rightToLeft="'+(I18N.lang==='ar'?1:0)+'"/></sheetViews><sheetData>'+rows.map((row,n)=>`<row r="${n+1}">`+row.map((value,j)=>`<c r="${String.fromCharCode(65+j)}${n+1}"${typeof value==='number'?'':' t="inlineStr"'}>`+(typeof value==='number'?'<v>'+value+'</v>':'<is><t xml:space="preserve">'+escape(value)+'</t></is>')+'</c>').join('')+'</row>').join('')+'</sheetData></worksheet>']));
 const chunks=[],central=[];let offset=0;
 const crc=data=>{let n=0xffffffff;for(const b of data){n^=b;for(let k=0;k<8;k++)n=(n>>>1)^((n&1)?0xedb88320:0);}return (n^0xffffffff)>>>0;};
 for(const [path,body]of files){const name=enc.encode(path),data=enc.encode(body),sum=crc(data),head=new Uint8Array(30+name.length),v=new DataView(head.buffer);v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint32(14,sum,true);v.setUint32(18,data.length,true);v.setUint32(22,data.length,true);v.setUint16(26,name.length,true);head.set(name,30);chunks.push(head,data);const dir=new Uint8Array(46+name.length),c=new DataView(dir.buffer);c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint32(16,sum,true);c.setUint32(20,data.length,true);c.setUint32(24,data.length,true);c.setUint16(28,name.length,true);c.setUint32(42,offset,true);dir.set(name,46);central.push(dir);offset+=head.length+data.length;}
 const end=new Uint8Array(22),view=new DataView(end.buffer);view.setUint32(0,0x06054b50,true);view.setUint16(8,files.length,true);view.setUint16(10,files.length,true);view.setUint32(12,central.reduce((n,b)=>n+b.length,0),true);view.setUint32(16,offset,true);return new Blob([...chunks,...central,end],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
const beforeFinanceFetch=window.fetch;
window.fetch=async function(input,init={}){
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(url.origin!==location.origin||url.pathname!=='/api/reports.finance.export')return beforeFinanceFetch(input,init);
 try{previewRequire('reports.view');const d=JSON.parse(init.body),report=await previewFinance(d);if(d.revision!==report.revision)throw Error(I18N.tr('reports.exportChanged'));return new Response(previewReportWorkbook(report,d),{status:200,headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}});}
 catch(e){return new Response(JSON.stringify({error:e.message}),{status:422,headers:{'Content-Type':'application/json'}});}
};
