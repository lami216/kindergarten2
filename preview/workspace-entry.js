/* This file is copied only into the disposable GitHub Pages build. */
'use strict';
const pagesLogin=liveLoginScreen;
function pagesLoginFields(){
 const form=$('#live-login');for(const input of form.querySelectorAll('input')){input.required=false;input.closest('label').hidden=true;input.value='';}
 $('#preview-enter').textContent='الدخول إلى المعاينة';
 if(!$('#pages-scope'))form.insertAdjacentHTML('afterend','<p id="pages-scope" class="muted">معاينة ببيانات وهمية مؤقتة داخل التبويب. لا تدخل بيانات أطفال أو كلمات مرور حقيقية.</p><button type="button" class="quiet" id="pages-worker">الدخول بحساب عامل أنشأته في المعاينة</button>');
 $('#pages-worker').onclick=()=>{for(const input of form.querySelectorAll('input')){input.closest('label').hidden=false;input.required=true;}$('#preview-enter').textContent='دخول حساب المعاينة';};
}
liveLoginScreen=function(){pagesLogin();pagesLoginFields();};pagesLoginFields();
const pagesToast=toast;toast=function(message,kind){pagesToast(message==='تم الحفظ في السجل الحقيقي.'?'تم الحفظ في المعاينة.':message,kind);};
document.querySelector('footer').insertAdjacentHTML('beforeend','<p class="muted">معاينة مؤقتة · <button type="button" class="quiet" id="pages-reset">إعادة بيانات المعاينة</button></p>');$('#pages-reset').onclick=()=>location.reload();
document.addEventListener('click',event=>{const a=event.target.closest('a');if(a?.getAttribute('href')?.startsWith('/api/')){event.preventDefault();toast('ملفات PDF والنسخ الاحتياطية تُصدر من البرنامج الفعلي؛ بيانات هذه المعاينة مؤقتة.','error');}},true);
