/* Reauthenticate in place. Never persist drafts, refresh their revisions, or replay writes. */
'use strict';
let renewingSession = false;
function requestSessionRenewal() {
  if (!liveSession || renewingSession) return;
  renewingSession = true;
  const dialog = document.createElement('dialog');dialog.id = 'session-recovery-dialog';
  dialog.innerHTML = `<div class="dialog-head"><h2>${I18N.tr('session.title')}</h2></div><p>${I18N.tr('session.explanation')}</p><form id="session-renew-form" class="body-space"><label>${I18N.tr('session.username')}<input name="username" readonly autocomplete="username" value="${esc(liveSession.user.username)}"></label><label class="body-space">${I18N.tr('session.password')}<input name="password" type="password" required autocomplete="current-password"></label><p class="error" role="alert"></p><div class="actions body-space"><button class="primary">${I18N.tr('session.resume')}</button><button type="button" class="secondary danger" id="session-leave">${I18N.tr('session.leave')}</button></div></form>`;
  dialog.oncancel = event => event.preventDefault();
  document.body.append(dialog);dialog.showModal();
  dialog.querySelector('[name=password]').focus();
  dialog.querySelector('#session-leave').onclick = () => {liveLoginScreen();};
}
const sessionCall = liveCall;
liveCall = async function(operation, data) {
  if (renewingSession && !['login','session'].includes(operation)) {
    const error = Error(I18N.tr('session.explanation'));error.code = 'session_expired';throw error;
  }
  try {return await sessionCall(operation,data);}
  catch (error) {
    if (liveSession && (error.code === 'session_expired' || error.status === 401)) requestSessionRenewal();
    throw error;
  }
};
const sessionSubmit = liveSubmit;
liveSubmit = async function(form) {
  if (form.id !== 'session-renew-form') return sessionSubmit(form);
  const old = liveSession.user, password = form.elements.password.value;
  try {
    await sessionCall('login',{username:old.username,password});
    const fresh = await sessionCall('session');
    // A role/password change invalidates the old editing context. Do not carry
    // a manager's draft into a different identity or a lower-privilege session.
    if (fresh.user.user_id !== old.user_id || fresh.user.auth_version !== old.auth_version ||
        JSON.stringify(fresh.user.permissions) !== JSON.stringify(old.permissions) || fresh.user.is_admin !== old.is_admin) {
      liveLoginScreen();await liveEnter();toast(I18N.tr('session.permissionsChanged'),'error');return;
    }
    liveSession = fresh;demoActor = liveUser(fresh.user);
    renewingSession = false;form.reset();document.querySelector('#session-recovery-dialog')?.remove();
    document.querySelectorAll('#content .error,dialog[open] .error').forEach(box => {
      if (box.textContent === I18N.message('انتهت جلسة الدخول؛ أعد تسجيل الدخول.')) box.textContent = '';
    });
    toast(I18N.tr('session.restored'));
  } finally {form.elements.password.value = '';}
};
const sessionLoginScreen = liveLoginScreen;
liveLoginScreen = function() {
  renewingSession = false;FormDrafts.clear();
  document.querySelector('#session-recovery-dialog')?.remove();sessionLoginScreen();
};
// Private downloads stay on the current page when the session has expired.
// The same response handling is used for JSON forms and exported files.
document.addEventListener('click',async event=>{
  const link=event.target.closest('a[href^="/api/"]');
  if(!link||!/^\/api\/(receipt\/\d+|download\/backup)$/.test(link.getAttribute('href'))||event.button||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();event.stopImmediatePropagation();
  if(renewingSession||link.dataset.downloading)return;
  link.dataset.downloading='true';link.setAttribute('aria-disabled','true');
  try{
    const response=await fetch(link.getAttribute('href'),{credentials:'same-origin',headers:{'X-App-Language':I18N.lang}});
    if(!response.ok){const value=await response.json().catch(()=>({}));throw liveResponseError(response,value);}
    const url=URL.createObjectURL(await response.blob()),download=document.createElement('a');
    download.href=url;download.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'download';
    download.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }catch(error){toast(error.message,'error');}
  finally{delete link.dataset.downloading;link.removeAttribute('aria-disabled');}
},true);
