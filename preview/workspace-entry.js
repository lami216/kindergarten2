/* This file is copied only into the disposable GitHub Pages build. */
'use strict';
const pagesLogin=liveLoginScreen;
function pagesLoginFields(){
 const form=$('#live-login');for(const input of form.querySelectorAll('input')){input.required=false;input.closest('label').hidden=true;input.value='';}
 $('#preview-enter').textContent=`${I18N.tr("ui.8a4371800e90")}`;
 if(!$('#pages-scope'))form.insertAdjacentHTML('afterend',`<p id="pages-scope" class="muted">${I18N.tr("ui.85bc707920e6")}</p><button type="button" class="quiet" id="pages-worker">${I18N.tr("ui.925a5e528ac3")}</button>`);
 $('#pages-worker').onclick=()=>{for(const input of form.querySelectorAll('input')){input.closest('label').hidden=false;input.required=true;}$('#preview-enter').textContent=`${I18N.tr("ui.17e99cb34baa")}`;};
}
liveLoginScreen=function(){pagesLogin();pagesLoginFields();};pagesLoginFields();
const pagesToast=toast;toast=function(message,kind){pagesToast(message===`${I18N.tr("ui.8f603dcbc07f")}`?`${I18N.tr("ui.90325beeb02b")}`:message,kind);};
document.querySelector('footer').insertAdjacentHTML('beforeend',`<p class="muted">${I18N.tr("ui.f1bb931d71b4")} <button type="button" class="quiet" id="pages-reset">${I18N.tr("ui.0de0cb7fc351")}</button></p>`);$('#pages-reset').onclick=()=>location.reload();
document.addEventListener('click',event=>{const a=event.target.closest('a');if(a?.getAttribute('href')?.startsWith('/api/')){event.preventDefault();toast(`${I18N.tr("ui.62392f4f68fe")}`,'error');}},true);
