/* Unsaved page forms stay in memory only; nothing private goes into storage. */
'use strict';
window.FormDrafts = (() => {
  const forms = '#student-form,#expense-form,#department-form,#demo-user-create';
  const initial = new WeakMap();
  const exits = 'nav [data-page],#demo-logout,#back-students,#open-archive,[data-back-active],[data-go],#home-student,#add-student,[data-profile],[data-archive-profile],[data-person-nav],[data-tool-tab],[data-report-mode],[data-demo-user],[data-record-type],[data-settle],#open-transfer';
  let pending = null, replay = false;
  const register = () => document.querySelectorAll(forms).forEach(form => {
    if (!initial.has(form)) initial.set(form, formSignature(form));
  });
  const dirty = () => [...document.querySelectorAll(forms)].filter(form =>
    !form.closest('dialog') && initial.has(form) && formSignature(form) !== initial.get(form));
  function close() {
    pending = null;
    document.querySelector('#draft-navigation-dialog')?.remove();
  }
  function confirmExit(target) {
    if (pending) return;
    pending = target;
    const dialog = document.createElement('dialog');dialog.id = 'draft-navigation-dialog';
    dialog.innerHTML = `<div class="dialog-head"><h2>${I18N.tr('draft.title')}</h2></div><p>${I18N.tr('ui.c2841c04da4f')}</p><div class="actions body-space"><button type="button" class="secondary" data-draft-keep>${I18N.tr('ui.30dc28305899')}</button><button type="button" class="danger" data-draft-discard>${I18N.tr('ui.dc80cb7603ef')}</button></div>`;
    const keep = () => {close();target.focus({preventScroll:true});};
    dialog.oncancel = event => {event.preventDefault();keep();};
    dialog.onclick = event => {if (event.target === dialog) keep();};
    dialog.querySelector('[data-draft-keep]').onclick = keep;
    dialog.querySelector('[data-draft-discard]').onclick = () => {
      dirty().forEach(form => initial.set(form, formSignature(form)));
      close();
      if (target.isConnected) {replay = true;try {target.click();} finally {replay = false;}}
    };
    document.body.append(dialog);dialog.showModal();dialog.querySelector('[data-draft-keep]').focus();
  }
  register();
  new MutationObserver(register).observe(document.querySelector('#content'), {childList:true,subtree:true});
  document.addEventListener('click', event => {
    const target = event.target.closest(exits);
    if (replay || !target || target.closest('dialog') || !dirty().length) return;
    event.preventDefault();event.stopImmediatePropagation();confirmExit(target);
  }, true);
  window.addEventListener('beforeunload', event => {
    if (dirty().length) {event.preventDefault();event.returnValue = '';}
  });
  return Object.freeze({dirty,clear:close});
})();
