/* One interface, two languages. Translate system copy, never stored user data. */
'use strict';
window.I18N = (() => {
  const catalog = window.APP_MESSAGES;
  if (!catalog) throw new Error('Missing language catalog');
  const storageKey = 'kg.language';
  let lang = 'ar';
  try { if (localStorage.getItem(storageKey) === 'fr') lang = 'fr'; } catch (_) {}
  const interpolate = (value, params = {}) => value.replace(/\{(p\d+|[a-zA-Z]\w*)\}/g, (match, key) => Object.hasOwn(params, key) ? String(params[key]) : match);
  const tr = (key, params) => {
    if (!catalog[key]) throw new Error('Missing translation: ' + key);
    return interpolate(catalog[key][lang], params);
  };
  const bySource = new Map(Object.values(catalog).map(message => [message.ar, message]));
  const sourceLabel = value => lang === 'fr' ? (bySource.get(String(value))?.fr ?? value) : value;
  const patterns = Object.values(catalog).filter(m => /\{p\d+\}/.test(m.ar)).sort((a,b)=>b.ar.replace(/\{p\d+\}/g,'').length-a.ar.replace(/\{p\d+\}/g,'').length).map(m => {
    const keys = [];
    const pattern = m.ar.split(/(\{p\d+\})/).map(part => {
      if (/^\{p\d+\}$/.test(part)) { keys.push(part.slice(1,-1)); return '(.+?)'; }
      return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('');
    return { regex: new RegExp('^'+pattern+'$','s'), keys, message:m };
  });
  function message(value) {
    value = String(value ?? '');
    if (lang !== 'fr') return value;
    if (bySource.has(value)) return sourceLabel(value);
    for (const p of patterns) {
      const match=value.match(p.regex);
      if (match) return interpolate(p.message.fr, Object.fromEntries(p.keys.map((key,i)=>[key,match[i+1]])));
    }
    // Only error messages use this fallback. User content never passes here.
    return /[\u0600-\u06ff]/.test(value) ? tr('ui.0cacd3c2894a') : value;
  }
  const fieldLabel = (key,fallback=key) => lang==='fr'&&catalog['field.'+key]?tr('field.'+key):sourceLabel(fallback);
  const enumLabel = value => sourceLabel(({regular:'دفع',exempt:'معفي',present:'حاضر',absent:'غائب',excused:'غائب بعذر'})[value] || value);
  document.documentElement.lang=lang;
  document.documentElement.dir=lang==='fr'?'ltr':'rtl';
  document.title=sourceLabel(document.title);
  document.cookie='kg_language='+lang+'; Path=/; SameSite=Strict'+(location.protocol==='https:'?'; Secure':'');
  document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=tr(el.dataset.i18n));
  for (const attr of ['alt','title','placeholder','aria-label']) {
    document.querySelectorAll('[data-i18n-'+attr+']').forEach(el=>el.setAttribute(attr,tr(el.getAttribute('data-i18n-'+attr))));
  }
  const label=document.createElement('div');label.className='language-picker';label.setAttribute('role','group');label.setAttribute('aria-label',tr('ui.6520b21edd4d'));
  for (const [code,title] of [['ar','العربية'],['fr','Français']]) {
    const button=document.createElement('button');button.type='button';button.textContent=title;button.lang=code;button.dir=code==='ar'?'rtl':'ltr';button.dataset.language=code;
    button.className='quiet';button.setAttribute('aria-pressed',String(lang===code));
    button.onclick=()=>{
      if(!document.body.classList.contains('login-mode')||code===lang)return;
      try { localStorage.setItem(storageKey,code); } catch (_) { return; }
      location.reload();
    };
    label.append(button);
  }
  document.querySelector('.login-card').prepend(label);
  return Object.freeze({lang,tr,sourceLabel,enumLabel,fieldLabel,message,
    number:value=>Number(value).toLocaleString(lang==='fr'?'fr-FR':'en-US',{maximumFractionDigits:2}),
    date:value=>lang==='fr'&&/^\d{4}-\d{2}-\d{2}$/.test(String(value))?String(value).split('-').reverse().join('/'):value});
})();
