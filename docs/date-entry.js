/* Shared date fields: visible day / month / two-digit year, canonical ISO value. */
'use strict';
window.DateEntry = (() => {
  const states = new WeakMap();
  const valueProperty = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
  const digits = value => value.replace(/[٠-٩۰-۹]/g, c => String(c.charCodeAt(0) - (c <= '٩' ? 1632 : 1776)));
  const text = key => I18N.tr(`date.${key}`);
  const pad = value => String(value).padStart(2, '0');

  function enhance(input) {
    if (states.has(input)) return;
    const monthOnly = input.type === 'month';
    const initialValue = input.value;
    const parser = document.createElement('input');parser.type = input.type;
    const label = input.labels?.[0]?.textContent.trim() || text('label');
    const group = document.createElement('span');
    group.className = 'date-entry' + (monthOnly ? ' date-entry-month' : '');
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    const make = (part, control) => {
      const box = document.createElement('span');box.className = 'date-entry-field';
      const caption = document.createElement('span');caption.className = 'date-entry-caption';caption.textContent = text(part);
      control.dataset.datePart = part;
      control.setAttribute('aria-label', label + ' — ' + text(part));
      box.append(caption, control);group.append(box);
      return control;
    };
    const numeric = () => {
      const el = document.createElement('input');el.type = 'text';el.inputMode = 'numeric';
      el.maxLength = 2;el.autocomplete = 'off';el.dir = 'ltr';return el;
    };
    const day = monthOnly ? null : make('day', numeric());
    if (day) day.placeholder = text('day');
    const month = make('month', document.createElement('select'));
    month.add(new Option(text('month'), ''));
    for (let n = 1; n <= 12; n++) month.add(new Option(text('month.' + n), pad(n)));
    const year = make('year', numeric());year.placeholder = '00';
    const yearBox = document.createElement('span');yearBox.className = 'date-entry-year';yearBox.dir = 'ltr';
    const prefix = document.createElement('span');prefix.className = 'date-entry-century';prefix.textContent = '20';prefix.setAttribute('aria-hidden', 'true');
    year.before(yearBox);yearBox.append(prefix, year);
    const error = document.createElement('span');error.className = 'date-entry-error';error.hidden = true;error.setAttribute('aria-live', 'polite');group.append(error);
    input.before(group);input.type = 'hidden';input.hidden = true;input.dataset.dateCanonical = '';
    const parts = [day, month, year].filter(Boolean);
    let updating = false, touched = false, committed = initialValue;
    let lastValueAttribute = input.getAttribute('value');
    const rawSet = value => {valueProperty.set.call(input, value);lastValueAttribute = input.getAttribute('value');};
    function validate() {
      const any = parts.some(p => p.value !== '');
      const required = input.required || any;
      for (const p of parts) {
        p.disabled = input.disabled || input.readOnly;p.required = required;
        p.setCustomValidity('');p.removeAttribute('aria-invalid');
      }
      let message = '', bad = day || month;
      const complete = parts.every(p => p.value !== '');
      let iso = '';
      if (!complete && required) message = text(monthOnly ? 'monthIncomplete' : 'incomplete');
      else if (complete) {
        const y = Number(prefix.textContent + year.value), m = Number(month.value), d = day ? Number(day.value) : 1;
        const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
        if (!/^\d{2}$/.test(year.value)) {message = text('yearInvalid');bad = year;}
        else if (day && (!/^\d{1,2}$/.test(day.value) || d < 1 || d > days)) message = text('invalid');
        else {
          iso = prefix.textContent + year.value + '-' + month.value + (day ? '-' + pad(d) : '');
          if (input.min && iso < input.min) {message = text('min').replace('{date}', I18N.date(input.min));iso = '';}
          if (input.max && iso > input.max) {message = text('max').replace('{date}', I18N.date(input.max));iso = '';}
        }
      }
      if (input.disabled || input.readOnly) message = '';
      if (message) {bad.setCustomValidity(message);bad.setAttribute('aria-invalid', 'true');}
      error.textContent = message;error.hidden = !message || !touched;
      return {iso: message ? '' : iso, valid: !message, empty: !any};
    }
    function sync() {
      if (updating) return;
      const value = valueProperty.get.call(input), match = value.match(/^(\d{2})(\d{2})-(\d{2})(?:-(\d{2}))?$/);
      prefix.textContent = match ? match[1] : '20';year.value = match ? match[2] : '';
      month.value = match ? match[3] : '';if (day) day.value = match ? match[4] || '' : '';
      delete input.dataset.dateDraft;
      validate();
    }
    Object.defineProperty(input, 'value', {
      configurable: true, get() {return valueProperty.get.call(this);},
      set(value) {parser.value = value;rawSet(parser.value);if (!updating) committed = valueProperty.get.call(this);sync();}
    });
    function update(event) {
      event.stopPropagation();
      if (event.target !== month) event.target.value = digits(event.target.value).replace(/\D/g, '');
      touched = event.type === 'change' || touched;
      const result = validate();
      if (!result.valid && !result.empty) input.dataset.dateDraft = JSON.stringify(parts.map(p => p.value));
      else delete input.dataset.dateDraft;
      updating = true;rawSet(result.iso);
      try {
        // Preserve dirty-form detection even while an unfinished date has no ISO value.
        input.dispatchEvent(new Event('input', {bubbles: true}));
      } finally {updating = false;}
    }
    // Let the person finish all three parts before a live filter reloads its page.
    group.addEventListener('focusout', event => {
      if (group.contains(event.relatedTarget)) return;
      const result = validate();
      if (result.valid && committed !== input.value) {
        committed = input.value;input.dispatchEvent(new Event('change', {bubbles: true}));
      }
    });
    for (const p of parts) {
      p.addEventListener('input', update);p.addEventListener('change', update);
      p.addEventListener('invalid', () => {touched = true;validate();});
    }
    input.addEventListener('input', () => {if (!updating) sync();});
    input.addEventListener('change', () => {committed = input.value;if (!updating) sync();});
    input.form?.addEventListener('reset', () => queueMicrotask(() => {touched = false;input.value = initialValue;}));
    states.set(input, {sync, group, parts, validate, valueAttributeChanged() {
      if (input.getAttribute('value') !== lastValueAttribute) {
        lastValueAttribute = input.getAttribute('value');committed = input.value;sync();
      }
    }});sync();
  }
  function refresh(root = document) {
    if (root.matches?.('input[type="date"], input[type="month"]')) enhance(root);
    root.querySelectorAll?.('input[type="date"], input[type="month"]').forEach(enhance);
  }
  refresh();
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') {
        const state = states.get(record.target);
        if (state) record.attributeName === 'value' ? state.valueAttributeChanged() : state.validate();
      }
      else for (const node of record.addedNodes) if (node.nodeType === 1) refresh(node);
    }
  }).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['value', 'min', 'max', 'required', 'disabled', 'readonly']});
  return Object.freeze({refresh});
})();
