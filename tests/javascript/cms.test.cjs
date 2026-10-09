/* Exercise the shipped enhancement against a small DOM, without browser tooling. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/templates/cms/static/cms.js', 'utf8');

function environment(multiple = true, initiallySelected = []) {
  const handlers = new Map(), timers = new Map();
  let timerId = 0;
  const artifacts = [
    {id: 'post/first', title: 'Same title', kind: 'post', lifecycle: 'planned'},
    {id: 'post/second', title: 'Same title', kind: 'post', lifecycle: 'draft'},
  ];
  class Element {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.attrs = {}; this.dataset = {}; this.listeners = {}; this.hidden = false; this.value = ''; this.textContent = ''; }
    setAttribute(name, value) { this.attrs[name] = value; }
    removeAttribute(name) { delete this.attrs[name]; }
    hasAttribute(name) { return name in this.attrs; }
    getAttribute(name) { return this.attrs[name]; }
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
    append(...children) {
      children.forEach(child => {
        if (child.parentNode) child.parentNode.children = child.parentNode.children.filter(node => node !== child);
        child.parentNode = this; this.children.push(child);
      });
    }
    replaceChildren(...children) { this.children = []; this.append(...children); }
    dispatchEvent(event) {
      event.target = this;
      for (const callback of this.listeners[event.type] || []) callback(event);
      if (event.bubbles) for (const callback of handlers.get(event.type) || []) callback(event);
      return !event.defaultPrevented;
    }
    closest(selector) {
      if (selector.includes('form[')) return this.form || null;
      if (selector === 'label') return this.label;
      if (selector === '[data-copy]' && this.dataset.copy) return this;
      return null;
    }
    focus() { this.focused = true; }
    select() { this.textSelected = true; }
    scrollIntoView() {}
  }
  class Option extends Element {
    constructor(text, value) { super('option'); this.textContent = text; this.value = value; this.selected = initiallySelected.includes(value); this.defaultSelected = this.selected; }
  }
  class Select extends Element {
    constructor() { super('select'); this.multiple = multiple; this.name = 'relations'; }
    get options() { return this.children; }
    get selectedOptions() { return this.options.filter(option => option.selected); }
    get value() { return this.selectedOptions?.[0]?.value || ''; }
    set value(value) { this.children?.forEach(option => option.selected = option.value === value); }
    add(option) { this.append(option); }
  }
  const select = new Select();
  if (!multiple) select.add(new Option('No linked content', ''));
  artifacts.forEach(item => select.add(new Option(`${item.title} · ${item.kind} · ${item.id} · ${item.lifecycle}`, item.id)));
  const label = new Element('label'); select.label = label;
  const search = new Element('input'), results = new Element(), chips = new Element(), status = new Element(), enhanced = new Element();
  const parts = {'[data-relationship-select]': select, '[data-relationship-enhanced]': enhanced,
    '[data-relationship-search]': search, '[data-relationship-results]': results,
    '[data-relationship-chips]': chips, '[data-relationship-status]': status};
  const picker = new Element(); picker.dataset.multiple = String(multiple); picker.querySelector = selector => parts[selector] || null;
  const form = new Element('form'); form.attrs['data-board-editor'] = ''; form.querySelector = () => null; form.querySelectorAll = selector => selector === 'input, textarea, select' ? [select] : [];
  select.form = form; search.form = form;
  const copy = new Element('button'); copy.dataset.copy = '/workspace/content/notebooks/posts/idea.ipynb';
  const prompts = [];
  const document = {
    querySelector: () => null,
    querySelectorAll: selector => selector === '[data-relationship]' ? [picker] : selector.startsWith('form[') ? [form] : [],
    getElementById: () => null,
    createElement: tag => new Element(tag),
    addEventListener: (name, callback) => { const list = handlers.get(name) || []; list.push(callback); handlers.set(name, list); },
  };
  class Event {
    constructor(type, options = {}) { Object.assign(this, {type, ...options}); }
    preventDefault() { this.defaultPrevented = true; }
    stopPropagation() { this.stopped = true; }
  }
  const window = {addEventListener() {}, alert() {}, confirm: () => true, prompt: (...args) => prompts.push(args)};
  vm.runInNewContext(source, {document, window, navigator: {}, location: {hash: ''}, Option, Event, AbortController,
    setTimeout: callback => { timers.set(++timerId, callback); return timerId; }, clearTimeout: id => timers.delete(id),
    fetch: async url => {
      const q = new URL(url, 'http://localhost').searchParams.get('q').toLowerCase();
      return {ok: true, json: async () => ({artifacts: artifacts.filter(item => item.title.toLowerCase().includes(q) || item.id.includes(q))})};
    },
  });
  async function flush() {
    for (let i = 0; i < 10; i++) {
      for (const [id, callback] of timers) { timers.delete(id); callback(); }
      await Promise.resolve();
    }
  }
  async function query(value) { search.value = value; search.dispatchEvent(new Event('input', {bubbles: true})); await flush(); }
  function key(value) { const event = new Event('keydown'); event.key = value; search.dispatchEvent(event); return event; }
  return {select, search, results, chips, status, enhanced, form, prompts, copy, handlers, Event, query, key, flush};
}

test('typing never becomes a link; keyboard selects exact IDs and preserves selection order', async () => {
  const env = environment();
  await env.query('Same');
  assert.equal(env.results.children.length, 2);
  assert.equal(env.search.attrs['aria-expanded'], 'true');
  assert.deepEqual(env.select.selectedOptions, []);
  env.key('ArrowDown'); env.key('ArrowDown'); env.key('Enter');
  assert.deepEqual(env.select.selectedOptions.map(option => option.value), ['post/second']);
  assert.equal(env.form.dataset.dirty, 'true');
  await env.query('Same');
  assert.equal(env.results.children.length, 1);
  env.key('ArrowDown'); env.key('Enter');
  assert.deepEqual(env.select.selectedOptions.map(option => option.value), ['post/second', 'post/first']);
  await env.query('Same');
  assert.equal(env.results.children.length, 0);
  assert.equal(env.status.textContent, 'No matching content.');
});

for (const multiple of [true, false]) {
  test(`clicking the focused search reopens suggestions after selection (${multiple ? 'multiple' : 'single'} links)`, async () => {
    const env = environment(multiple);
    env.search.focus();
    env.search.dispatchEvent(new env.Event('focus'));
    await env.flush();
    env.results.children[0].dispatchEvent(new env.Event('click'));
    assert.equal(env.search.focused, true);
    assert.equal(env.results.hidden, true);
    assert.deepEqual(env.select.selectedOptions.map(option => option.value), ['post/first']);

    // The input is still focused, so this click does not produce another focus event.
    env.search.dispatchEvent(new env.Event('click'));
    await env.flush();
    assert.equal(env.results.hidden, false);
    assert.equal(env.search.attrs['aria-expanded'], 'true');
    assert.equal(env.results.children.length, 1);
    assert.ok(env.results.children[0].textContent.includes('post/second'));
    assert.deepEqual(env.select.selectedOptions.map(option => option.value), ['post/first']);

    env.key('Escape');
    env.search.dispatchEvent(new env.Event('click'));
    await env.flush();
    assert.equal(env.results.hidden, false);
    env.key('ArrowDown'); env.key('Enter');
    assert.deepEqual(env.select.selectedOptions.map(option => option.value), multiple ? ['post/first', 'post/second'] : ['post/second']);
  });
}

test('Escape cancels pending suggestions and clicking can reopen them', async () => {
  const env = environment();
  env.search.focus();
  env.search.dispatchEvent(new env.Event('focus'));
  env.key('Escape');
  await env.flush();
  assert.equal(env.results.hidden, true);
  assert.equal(env.search.attrs['aria-expanded'], 'false');
  assert.equal(env.status.textContent, '');

  env.search.value = 'Same';
  env.search.dispatchEvent(new env.Event('input', {bubbles: true}));
  env.key('Escape');
  await env.flush();
  assert.equal(env.results.hidden, true);

  env.search.dispatchEvent(new env.Event('click'));
  await env.flush();
  assert.equal(env.results.hidden, false);
  assert.equal(env.results.children.length, 2);
});

test('Escape dismisses suggestions without dismissing a dialog; single links replace and clear', async () => {
  const env = environment(false, ['post/first']);
  await env.query('second');
  const escaped = env.key('Escape');
  assert.equal(escaped.stopped, true);
  assert.equal(env.results.hidden, true);
  assert.deepEqual(env.select.selectedOptions.map(option => option.value), ['post/first']);
  await env.query('second'); env.key('ArrowDown'); env.key('Enter');
  assert.deepEqual(env.select.selectedOptions.map(option => option.value), ['post/second']);
  env.chips.children[0].children[1].dispatchEvent(new env.Event('click'));
  assert.equal(env.select.value, '');
  assert.equal(env.chips.children.length, 0);
});

test('clipboard failure offers the canonical source path for manual copying', async () => {
  const env = environment();
  const event = new env.Event('click'); event.target = env.copy;
  for (const callback of env.handlers.get('click')) await callback(event);
  assert.deepEqual(env.prompts, [['Copy canonical source path', env.copy.dataset.copy]]);
});

test('header controls follow their associated editor through edit and save states', async () => {
  const handlers = new Map();
  const fields = {disabled: false}, status = {textContent: ''};
  const input = {name: 'title', value: 'Saved title', focus() {}};
  const form = {
    id: 'data-editor-form', dataset: {initialized: 'true', editing: 'false', dirty: 'false'},
    savedValues: JSON.stringify([['title', 'Saved title']]),
    hasAttribute: () => false,
    matches: selector => ['[data-editor]', 'form[data-editor]'].includes(selector),
    closest: selector => selector.startsWith('form') ? form : null,
    querySelector: selector => selector === '[data-editor-fields]' ? fields :
      selector === '[data-edit-status]' ? status : selector.startsWith('input') ? input : null,
    querySelectorAll: selector => selector === 'input, textarea, select' ? [input] : [],
  };
  input.closest = selector => selector.startsWith('form') ? form : null;
  const save = {hasAttribute: () => false};
  const savePublish = {hasAttribute: () => false};
  const blockedPublish = {hasAttribute: key => key === 'data-blocked'};
  const taskHint = {textContent: ''};
  const task = {closest: () => ({querySelector: () => taskHint})};
  const cancel = {attrs: {}, setAttribute(key, value) { this.attrs[key] = value; }};
  const edit = {form, closest: selector => selector === '[data-begin-edit]' ? edit : null};
  const toolbar = {
    querySelector: selector => selector === '[data-save]' ? save : selector === '[data-cancel]' ? cancel : null,
    querySelectorAll: selector => selector === '[data-begin-edit]' ? [edit] : selector === '[data-save]' ? [save, savePublish, blockedPublish] : [],
  };
  const document = {
    querySelector: selector => selector === '[data-editor-toolbar="data-editor-form"]' ? toolbar : null,
    querySelectorAll: selector => selector === '[data-summary-task]' ? [task] : selector.startsWith('form[') ? [form] : [],
    getElementById: () => null,
    addEventListener: (name, callback) => {
      const list = handlers.get(name) || []; list.push(callback); handlers.set(name, list);
    },
  };
  vm.runInNewContext(source, {document, window: {addEventListener() {}}, location: {hash: ''}});
  assert.equal(edit.hidden, false);
  assert.equal(save.hidden, true);
  assert.equal(cancel.hidden, true);
  assert.equal(fields.disabled, true);
  assert.equal(task.disabled, false);
  for (const callback of handlers.get('click')) await callback({target: edit});
  assert.equal(form.dataset.editing, 'true');
  assert.equal(edit.hidden, true);
  assert.equal(save.hidden, false);
  assert.equal(cancel.hidden, false);
  assert.equal(fields.disabled, false);
  input.value = 'Unsaved title';
  for (const callback of handlers.get('input')) callback({target: input});
  assert.equal(form.dataset.dirty, 'true');
  assert.equal(task.disabled, true);
  assert.match(taskHint.textContent, /Save your changes first/);
  assert.equal(savePublish.disabled, false);
  assert.equal(blockedPublish.disabled, true);
  for (const callback of handlers.get('htmx:beforeRequest')) callback({detail: {elt: form}});
  assert.equal(save.disabled, true);
  assert.equal(savePublish.disabled, true);
  assert.equal(cancel.attrs['aria-disabled'], 'true');
  assert.equal(fields.disabled, true);
  for (const callback of handlers.get('htmx:afterRequest')) callback({detail: {elt: form, failed: false}});
  assert.equal(save.disabled, false);
  assert.equal(savePublish.disabled, false);
  assert.equal(blockedPublish.disabled, true);
  assert.equal(cancel.attrs['aria-disabled'], 'false');
  assert.equal(fields.disabled, false);
  input.value = 'Saved title';
  for (const callback of handlers.get('input')) callback({target: input});
  assert.equal(task.disabled, false);
  const taskForm = {closest: () => taskForm, matches: selector => selector.includes('[data-summary-task-form]')};
  for (const callback of handlers.get('htmx:beforeRequest')) callback({detail: {elt: taskForm}});
  assert.equal(task.disabled, true);
  assert.equal(fields.disabled, true);
  for (const callback of handlers.get('htmx:afterRequest')) callback({detail: {elt: taskForm, failed: false}});
  assert.equal(task.disabled, false);
});

function workspaceEnvironment(hash = '') {
  const handlers = new Map();
  const windowHandlers = new Map();
  const location = {hash};
  function element(id) {
    return {id, attrs: {}, dataset: {}, listeners: {}, hidden: false,
      setAttribute(key, value) { this.attrs[key] = value; },
      addEventListener(key, callback) { this.listeners[key] = callback; },
      querySelector() { return null; }, focus() { this.focused = true; },
      closest(selector) { return selector === '[data-workspace-pane]' ? this : null; },
      matches() { return false; },
    };
  }
  const panes = ['site-fields', 'planning-fields', 'internal-fields'].map(element);
  const inputs = panes.map(pane => ({name: pane.id, value: '', disabled: false}));
  const fields = {disabled: false};
  const form = {
    id: 'artifact-editor-form', dataset: {editing: 'true'},
    hasAttribute: () => false, closest: () => null,
    querySelector: selector => selector === '[data-editor-fields]' ? fields : null,
    querySelectorAll: selector => selector === 'input, textarea, select' ? inputs : [],
  };
  let links, nav;
  function replaceNav() {
    links = panes.map(pane => Object.assign(element(pane.id + '-tab'), {hash: '#' + pane.id}));
    nav = element('nav'); nav.dataset.defaultPane = 'site-fields';
    nav.querySelectorAll = () => links;
  }
  replaceNav();
  const document = {
    querySelector: () => null,
    querySelectorAll: selector => selector === '[data-workspace-tabs]' ? [nav] : selector.startsWith('form[') ? [form] : [],
    getElementById: id => panes.find(pane => pane.id === id) || null,
    addEventListener: (name, callback) => {
      const list = handlers.get(name) || []; list.push(callback); handlers.set(name, list);
    },
  };
  vm.runInNewContext(source, {document, location, history: {replaceState(_, __, hash) { location.hash = hash; }},
    window: {addEventListener(name, callback) { windowHandlers.set(name, callback); }},
  });
  function click(index) { links[index].listeners.click({preventDefault() {}}); }
  function key(index, key) { links[index].listeners.keydown({key, preventDefault() {}}); }
  function swap() {
    replaceNav();
    for (const callback of handlers.get('htmx:afterSwap')) callback({detail: {target: {id: 'artifact-editor'}}});
  }
  return {panes, inputs, fields, form, get links() { return links; }, click, key, swap, location, handlers, windowHandlers};
}

test('workspace tabs retain controls, support keyboard navigation and survive HTMX replacement', () => {
  const env = workspaceEnvironment('#internal-fields');
  assert.deepEqual(env.panes.map(pane => pane.hidden), [true, true, false]);
  env.inputs[2].value = 'An unsaved note';
  env.click(0);
  assert.deepEqual(env.panes.map(pane => pane.hidden), [false, true, true]);
  assert.equal(env.inputs[2].value, 'An unsaved note');
  assert.equal(env.inputs[2].disabled, false);
  assert.equal(env.fields.disabled, false);
  assert.equal(env.form.querySelectorAll('input, textarea, select').length, 3);
  env.key(0, 'ArrowLeft');
  assert.equal(env.links[2].attrs['aria-selected'], 'true');
  assert.equal(env.links[2].focused, true);
  env.key(2, 'Home');
  assert.equal(env.links[0].tabIndex, 0);
  env.key(0, 'End');
  env.swap();
  assert.equal(env.links[2].attrs['aria-selected'], 'true');
  assert.equal(env.location.hash, '#internal-fields');
});

test('native validation exposes a required control in another workspace pane', () => {
  const env = workspaceEnvironment();
  const details = {open: false};
  const target = {closest(selector) { return selector === 'details' ? details : env.panes[2]; }};
  for (const callback of env.handlers.get('invalid')) callback({target});
  assert.equal(env.panes[2].hidden, false);
  assert.equal(details.open, true);
});
