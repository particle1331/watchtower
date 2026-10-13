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

function dialogEnvironment() {
  const handlers = new Map();
  class Dialog {
    constructor(id) { this.id = id; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.open = false; }
    querySelectorAll() { return []; }
    querySelector(selector) { return selector === 'form[data-board-editor]' ? this.form : null; }
    hasAttribute(name) { return name in this.attrs; }
    removeAttribute(name) { delete this.attrs[name]; }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    contains(dialog) { return dialog.parent === this; }
    showModal() { this.open = true; }
    close() { this.open = false; this.listeners.close?.(); }
    closest() { return null; }
  }
  const view = new Dialog('view'), edit = new Dialog('edit'), notes = new Dialog('notes');
  notes.parent = view;
  const dialogs = {view, edit, notes};
  const document = {
    querySelector: () => null,
    querySelectorAll: selector => selector === 'dialog.cms-dialog' ? Object.values(dialogs) : [],
    getElementById: id => dialogs[id] || null,
    addEventListener: (name, callback) => { const list = handlers.get(name) || []; list.push(callback); handlers.set(name, list); },
  };
  const confirmations = [];
  const window = {addEventListener() {}, confirm(message) { confirmations.push(message); return window.allowDiscard; }};
  vm.runInNewContext(source, {document, window, location: {hash: ''}, HTMLDialogElement: Dialog});
  function link(target, parent = null) {
    return {
      dataset: {dialogOpen: target}, focused: false,
      closest(selector) { return selector === '[data-dialog-open]' ? this : selector === 'dialog' ? parent : null; },
      focus() { this.focused = true; },
    };
  }
  async function click(target) {
    const event = {target, preventDefault() { this.defaultPrevented = true; }};
    for (const callback of handlers.get('click')) await callback(event);
    return event;
  }
  function cancel(dialog) { dialog.listeners.cancel({preventDefault() {}}); }
  return {view, edit, notes, window, confirmations, link, click, cancel};
}

test('card details hand off to Edit and restore focus to the board card on Escape', async () => {
  const env = dialogEnvironment();
  const tile = env.link('view');
  assert.equal((await env.click(tile)).defaultPrevented, true);
  assert.equal(env.view.open, true);
  await env.click(env.link('edit', env.view));
  assert.equal(env.view.open, false);
  assert.equal(env.edit.open, true);
  assert.equal(env.edit.opener, tile);
  env.cancel(env.edit);
  assert.equal(env.edit.open, false);
  assert.equal(tile.focused, true);
});

test('linked notes remain above card details and return focus to their opener', async () => {
  const env = dialogEnvironment();
  await env.click(env.link('view'));
  const notesLink = env.link('notes', env.view);
  await env.click(notesLink);
  assert.equal(env.view.open, true);
  assert.equal(env.notes.open, true);
  env.cancel(env.notes);
  assert.equal(env.notes.open, false);
  assert.equal(env.view.open, true);
  assert.equal(notesLink.focused, true);
});

test('dialog handoff respects unsaved edits before opening another card dialog', async () => {
  const env = dialogEnvironment();
  env.edit.form = {dataset: {dirty: 'true'}, reset() { this.resetCount = (this.resetCount || 0) + 1; }, removeAttribute() {}};
  await env.click(env.link('edit'));
  await env.click(env.link('view', env.edit));
  assert.equal(env.edit.open, true);
  assert.equal(env.view.open, false);
  assert.equal(env.edit.form.resetCount, undefined);
  assert.equal(env.confirmations.length, 1);
  env.window.allowDiscard = true;
  await env.click(env.link('view', env.edit));
  assert.equal(env.edit.open, false);
  assert.equal(env.edit.form.resetCount, 1);
  assert.equal(env.view.open, true);
});


function todoEnvironment() {
  const handlers = new Map();
  let form;
  class Event {
    constructor(type, options = {}) { this.type = type; Object.assign(this, options); }
    preventDefault() { this.defaultPrevented = true; }
  }
  class Element {
    constructor(name = '', type = 'text') {
      this.name = name; this.type = type; this.value = ''; this.checked = false;
      this.hidden = false; this.dataset = {}; this.listeners = {}; this.parts = {};
    }
    querySelector(selector) { return this.parts[selector] || null; }
    querySelectorAll() { return []; }
    hasAttribute() { return false; }
    closest(selector) { return selector.includes('form[') ? form : null; }
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
    dispatchEvent(event) {
      event.target = this;
      for (const callback of this.listeners[event.type] || []) callback(event);
      if (event.bubbles) for (const callback of handlers.get(event.type) || []) callback(event);
    }
    focus() { this.focused = true; }
    remove() { list.children = list.children.filter(row => row !== this); }
  }
  function row(text, done) {
    const item = new Element(), check = new Element('todo_done', 'checkbox');
    check.checked = done;
    const content = new Element('todo_text'); content.value = text;
    const discard = new Element('todo_remove', 'checkbox');
    item.parts = {'[data-todo-done]': check, '[data-todo-text]': content,
      '[data-todo-discard]': discard, '[data-todo-remove]': new Element(),
      '[data-todo-remove-fallback]': new Element()};
    item.cloneNode = () => row('', false);
    return item;
  }
  const list = new Element(); list.children = Array.from({length: 8}, (_, i) => row(`Item ${i}`, i < 7));
  list.querySelectorAll = () => list.children;
  list.append = item => list.children.push(item);
  const editor = new Element(), count = new Element(), input = new Element('todo_new'), add = new Element(), empty = new Element();
  const template = {content: {firstElementChild: row('', false)}};
  editor.parts = {'[data-todo-list]': list, '[data-todo-count]': count, '[data-todo-new]': input,
    '[data-todo-add]': add, '[data-todo-empty]': empty, '[data-todo-template]': template};
  form = new Element(); form.dataset.editing = 'true';
  form.querySelectorAll = selector => selector === 'input, textarea, select' ?
    [input, ...list.children.flatMap(item => ['[data-todo-done]', '[data-todo-text]', '[data-todo-discard]'].map(key => item.parts[key]))] : [];
  const document = {
    querySelector: () => null, getElementById: () => null,
    querySelectorAll(selector) {
      if (selector === '[data-todo-editor]') return [editor];
      if (selector === 'form[data-editor], form[data-board-editor], form[data-outline-form]') return [form];
      return [];
    },
    addEventListener(name, callback) { const list = handlers.get(name) || []; list.push(callback); handlers.set(name, list); },
  };
  const window = {addEventListener() {}};
  vm.runInNewContext(source, {document, window, Event, location: {hash: ''}});
  return {list, input, add, count, empty, form, Event, initialize: () => handlers.get('htmx:afterSwap')[0]({detail: {target: {id: 'artifact-editor'}}})};
}

test('entity checklist updates its fraction, rejects blank additions, and marks edits dirty', () => {
  const env = todoEnvironment();
  assert.equal(env.count.textContent, '7/8');
  assert.equal(env.form.dataset.dirty, 'false');
  env.add.dispatchEvent(new env.Event('click'));
  assert.equal(env.list.children.length, 8);
  env.input.value = '  New item  ';
  const enter = new env.Event('keydown', {key: 'Enter'});
  env.input.dispatchEvent(enter);
  assert.equal(enter.defaultPrevented, true);
  assert.equal(env.count.textContent, '7/9');
  assert.equal(env.list.children[8].parts['[data-todo-text]'].value, 'New item');
  assert.equal(env.form.dataset.dirty, 'true');
  const done = env.list.children[8].parts['[data-todo-done]'];
  done.checked = true; done.dispatchEvent(new env.Event('change', {bubbles: true}));
  assert.equal(env.count.textContent, '8/9');
  env.list.children[0].parts['[data-todo-remove]'].dispatchEvent(new env.Event('click'));
  assert.equal(env.count.textContent, '7/8');
  assert.deepEqual(env.list.children.map(item => item.parts['[data-todo-done]'].value), Array.from({length: 8}, (_, i) => String(i)));
  // Re-initialization after a swap never discards local rows or registers duplicate handlers.
  env.initialize();
  assert.equal(env.count.textContent, '7/8');
  while (env.list.children.length) env.list.children[0].parts['[data-todo-remove]'].dispatchEvent(new env.Event('click'));
  assert.equal(env.count.textContent, '0/0');
  assert.equal(env.empty.hidden, false);
});

function kanbanEnvironment() {
  const handlers = new Map(), alerts = [], requests = [];
  let resolveRequest, rejectRequest;
  class Element {
    constructor(dataset = {}, parent = null) {
      this.dataset = dataset; this.listeners = {}; this.hidden = false; this.children = []; this.parts = {}; this.attrs = {};
      const classes = new Set();
      this.classList = {add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name)};
      if (parent) parent.insertBefore(this, null);
    }
    get parentElement() { return this.parent; }
    get parentNode() { return this.parent; }
    get nextSibling() { return this.parent?.children[this.parent.children.indexOf(this) + 1] || null; }
    insertBefore(child, before) {
      if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1);
      const index = before ? this.children.indexOf(before) : this.children.length;
      this.children.splice(index, 0, child); child.parent = this;
    }
    getAttribute(name) { return this.attrs[name]; }
    closest(selector) {
      if (selector === '[data-kanban-card]' && this.dataset.kanbanCard) return this;
      if (selector === '[data-kanban-column]' && this.dataset.kanbanColumn) return this;
      if (selector === 'button, input, textarea, select, .kanban-card-footer') return this.interactive ? this : null;
      return this.parent?.closest(selector) || null;
    }
    contains(element) { return element === this || !!element?.parent && this.contains(element.parent); }
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
    querySelector(selector) { return this.parts[selector] || this.querySelectorAll(selector)[0] || null; }
    querySelectorAll(selector) {
      const descendants = this.children.flatMap(child => [child, ...child.querySelectorAll('*')]);
      if (selector === '*') return descendants;
      if (selector === '[data-kanban-card]') return descendants.filter(child => child.dataset.kanbanCard);
      return [];
    }
    hasAttribute(name) { return name in this.attrs; }
  }
  const board = new Element(), hint = new Element(), status = new Element(), reload = new Element();
  hint.hidden = status.hidden = reload.hidden = true;
  const columns = ['todo', 'in-progress', 'review', 'done'].map(id => new Element({kanbanColumn: id}, board));
  const titles = ['To do', 'In progress', 'Review', 'Done'];
  const lists = columns.map((column, index) => {
    const list = new Element({}, column), empty = new Element({}, list), count = new Element();
    column.attrs['aria-label'] = titles[index];
    column.parts = {'[data-client-list]': list, '[data-kanban-count]': count};
    list.parts = {'[data-kanban-empty]': empty};
    list.refreshList = revealed => list.revealed = revealed;
    return list;
  });
  const card = new Element({kanbanCard: 'task-one', kanbanOrder: '1'}, lists[0]), link = new Element({}, card), footer = new Element({}, card);
  footer.interactive = true;
  card.querySelectorAll = selector => selector === 'a' ? [link] : [];
  board.parts = {'[data-kanban-drag-hint]': hint, '[data-kanban-move-status]': status, '[data-kanban-reload]': reload};
  function columnSelect() {
    return {name: 'column', type: 'select-one', value: 'todo', disabled: false,
      options: columns.map(column => ({value: column.dataset.kanbanColumn, defaultSelected: column === columns[0]}))};
  }
  const select = columnSelect(), editSelect = columnSelect(), revision = {value: 'kanban:saved-board', disabled: false}, editRevision = {value: revision.value, disabled: false};
  const controls = [select, editSelect, revision, editRevision];
  const queryAll = board.querySelectorAll.bind(board);
  board.querySelectorAll = selector => selector === '[data-kanban-column]' ? columns :
    selector === 'input[name="revision"]' ? [revision, editRevision] :
      selector === 'form input, form textarea, form select, form button' ? controls : queryAll(selector);
  const editor = new Element(); editor.attrs['data-board-editor'] = '';
  editor.parts = {'select[name="column"]': editSelect};
  editor.querySelectorAll = selector => selector === 'input, textarea, select' ? [editSelect] : [];
  const submissions = [];
  const form = {
    querySelector: selector => selector === 'select[name="column"]' ? select : selector === 'input[name="revision"]' ? revision : selector === 'input[name="card_id"]' ? {value: card.dataset.kanbanCard} : null,
    matches: selector => selector === 'form[data-kanban-move]',
    requestSubmit() {
      const event = {target: form, preventDefault() { this.defaultPrevented = true; }};
      const pending = (board.listeners.submit || []).map(callback => callback(event));
      for (const callback of handlers.get('submit') || []) callback(event);
      if (!event.defaultPrevented) submissions.push({card_id: card.dataset.kanbanCard, column: select.value, revision: revision.value});
      return Promise.all(pending);
    },
  };
  const badge = new Element(), view = new Element(), edit = new Element();
  view.parts = {'form[data-kanban-move]': form, '[data-kanban-card-column]': badge};
  edit.parts = {'form[data-board-editor]': editor};
  const document = {
    querySelector: () => null,
    querySelectorAll(selector) {
      if (selector === '[data-kanban-board]') return [board];
      if (selector === 'form[data-editor], form[data-board-editor], form[data-outline-form]') return [editor];
      return [];
    },
    getElementById: id => id === 'view-task-one' ? view : id === 'edit-task-one' ? edit : null,
    addEventListener(name, callback) { const list = handlers.get(name) || []; list.push(callback); handlers.set(name, list); },
  };
  const window = {addEventListener() {}, alert: message => alerts.push(message)};
  vm.runInNewContext(source, {document, window, location: {hash: ''}, fetch: (url, options) => {
    requests.push({url, method: options.method, revision: options.headers['If-Match'], patch: JSON.parse(options.body)});
    return new Promise((resolve, reject) => { resolveRequest = resolve; rejectRequest = reject; });
  }});
  const transfer = {setData(type, value) { this[type] = value; }};
  function fire(type, target, extra = {}) {
    const event = {target, dataTransfer: transfer, preventDefault() { this.defaultPrevented = true; }, ...extra};
    event.completion = Promise.all((board.listeners[type] || []).map(callback => callback(event)));
    return event;
  }
  return {board, hint, status, reload, card, link, footer, columns, lists, editor, form, select, editSelect, revision, editRevision, badge, controls, transfer, submissions, requests, alerts, fire,
    respond: (code = 200, result = {board_revision: 'kanban:next-board'}) => resolveRequest({ok: code === 200, status: code, json: async () => result}),
    fail: () => rejectRequest(new Error('Network disconnected')),
    addCard: (id, order, column) => new Element({kanbanCard: id, kanbanOrder: String(order)}, lists[column]),
    initialize: () => handlers.get('htmx:afterSwap')[0]({detail: {target: {id: 'kanban-board'}}})};
}

test('a drop moves the card immediately and saves in the background without navigation', async () => {
  const env = kanbanEnvironment();
  assert.equal(env.card.draggable, true);
  assert.equal(env.link.draggable, false);
  assert.equal(env.hint.hidden, false);
  env.fire('pointerdown', env.link);
  assert.equal(env.fire('dragstart', env.card).defaultPrevented, undefined);
  assert.equal(env.transfer.effectAllowed, 'move');
  assert.equal(env.transfer['text/plain'], 'task-one');
  assert.equal(env.card.classList.contains('is-dragging'), true);
  assert.equal(env.fire('dragover', env.columns[2]).defaultPrevented, true);
  assert.equal(env.transfer.dropEffect, 'move');
  assert.equal(env.columns[2].classList.contains('is-drop-target'), true);
  const drop = env.fire('drop', env.columns[2]);
  assert.deepEqual(env.submissions, []);
  assert.deepEqual(env.requests, [{url: '/api/kanban/task-one', method: 'PATCH', revision: 'kanban:saved-board', patch: {column: 'review'}}]);
  assert.equal(env.card.parent, env.lists[2]);
  assert.equal(env.columns[0].parts['[data-kanban-count]'].textContent, 0);
  assert.equal(env.columns[2].parts['[data-kanban-count]'].textContent, 1);
  assert.equal(env.lists[0].parts['[data-kanban-empty]'].hidden, false);
  assert.equal(env.lists[2].parts['[data-kanban-empty]'].hidden, true);
  assert.equal(env.card.classList.contains('is-saving'), true);
  assert.equal(env.revision.value, 'kanban:saved-board');
  assert.equal(env.controls.every(control => control.disabled), true);
  assert.equal(env.card.classList.contains('is-dragging'), false);
  assert.equal(env.columns[2].classList.contains('is-drop-target'), false);
  assert.equal(env.fire('dragstart', env.card).defaultPrevented, true);
  env.respond(); await drop.completion;
  assert.equal(env.revision.value, 'kanban:next-board');
  assert.equal(env.editRevision.value, env.revision.value);
  assert.equal(env.select.value, 'review');
  assert.equal(env.editSelect.value, 'review');
  assert.equal(env.editSelect.options.find(option => option.defaultSelected).value, 'review');
  assert.equal(env.badge.textContent, 'Review');
  assert.equal(env.status.textContent, 'Moved to Review.');
  assert.equal(env.controls.every(control => !control.disabled), true);
  assert.equal(env.card.classList.contains('is-saving'), false);
  assert.equal(env.editor.dataset.dirty, 'false');
  env.fire('dragstart', env.card);
  const again = env.fire('drop', env.columns[1]);
  assert.equal(env.requests[1].revision, 'kanban:next-board');
  env.respond(200, {board_revision: 'kanban:third-board'}); await again.completion;
  assert.equal(env.card.parent, env.lists[1]);
});

test('same-column, cancelled, and external drops never save a move', () => {
  const env = kanbanEnvironment();
  assert.equal(env.fire('dragover', env.columns[2]).defaultPrevented, undefined);
  env.fire('drop', env.columns[2]);
  env.fire('dragstart', env.card);
  env.fire('dragover', env.columns[0]);
  assert.equal(env.transfer.dropEffect, 'none');
  env.fire('drop', env.columns[0]);
  env.fire('dragstart', env.card);
  env.fire('dragover', env.columns[3]);
  env.fire('dragleave', env.columns[3], {relatedTarget: null});
  assert.equal(env.columns[3].classList.contains('is-drop-target'), false);
  env.fire('dragend', env.card);
  env.fire('drop', env.columns[3]);
  assert.deepEqual(env.submissions, []);
  assert.deepEqual(env.requests, []);
  assert.equal(env.card.classList.contains('is-dragging'), false);
});

test('unsaved card edits block both dragging and Move without losing the edits', async () => {
  const env = kanbanEnvironment();
  env.editor.dataset.dirty = 'true';
  assert.equal(env.fire('dragstart', env.card).defaultPrevented, true);
  await env.form.requestSubmit();
  assert.equal(env.editor.dataset.dirty, 'true');
  assert.deepEqual(env.submissions, []);
  assert.equal(env.alerts.length, 2);
  env.editor.dataset.dirty = 'false';
  env.fire('dragstart', env.card);
  env.editor.dataset.dirty = 'true';
  env.fire('drop', env.columns[2]);
  assert.deepEqual(env.submissions, []);
  assert.equal(env.card.classList.contains('is-dragging'), false);
});

test('card footer actions do not start drags and swapped boards initialize only once', async () => {
  const env = kanbanEnvironment();
  env.fire('pointerdown', env.footer);
  assert.equal(env.fire('dragstart', env.card).defaultPrevented, true);
  env.fire('pointerdown', env.link);
  env.initialize();
  env.fire('dragstart', env.card);
  const drop = env.fire('drop', env.columns[1]);
  assert.equal(env.requests.length, 1);
  env.respond(); await drop.completion;
  assert.deepEqual(env.submissions, []);
});

for (const failure of [412, 500, 'network']) {
  test(`failed background move restores the exact position and requires reconciliation (${failure})`, async () => {
    const env = kanbanEnvironment();
    const neighbor = env.addCard('neighbor', 2, 0);
    env.controls[3].disabled = true;
    env.fire('dragstart', env.card);
    const drop = env.fire('drop', env.columns[3]);
    assert.equal(env.card.parent, env.lists[3]);
    if (failure === 'network') env.fail();
    else env.respond(failure, {error: {message: 'Save failed'}});
    await drop.completion;
    assert.equal(env.card.parent, env.lists[0]);
    assert.equal(env.card.nextSibling, neighbor);
    assert.equal(env.columns[0].parts['[data-kanban-count]'].textContent, 2);
    assert.equal(env.columns[3].parts['[data-kanban-count]'].textContent, 0);
    assert.equal(env.lists[3].parts['[data-kanban-empty]'].hidden, false);
    assert.equal(env.revision.value, 'kanban:saved-board');
    assert.equal(env.reload.hidden, false);
    assert.match(env.status.textContent, /Move to Done was not confirmed/);
    if (failure === 412) assert.match(env.status.textContent, /board changed/);
    assert.equal(env.controls[3].disabled, true);
    assert.equal(env.fire('dragstart', env.card).defaultPrevented, true);
    assert.equal(env.requests.length, 1);
  });
}

test('background moves preserve saved card ordering and keep the dialog Move control in place', async () => {
  const env = kanbanEnvironment();
  const older = env.addCard('older', 0, 2), newer = env.addCard('newer', 2, 2);
  env.select.value = 'review';
  const submitted = env.form.requestSubmit();
  assert.deepEqual(env.lists[2].querySelectorAll('[data-kanban-card]'), [older, env.card, newer]);
  assert.equal(env.lists[2].revealed, env.card);
  env.respond(); await submitted;
  assert.deepEqual(env.submissions, []);
  assert.equal(env.requests.length, 1);
});

test('column pagination updates after moving cards and preserves scroll position', () => {
  const handlers = new Map();
  const control = () => ({listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; }});
  const parts = Object.fromEntries(['[data-count]', '[data-page]', '[data-previous]', '[data-next]', 'select'].map(key => [key, control()]));
  const toolbar = {setAttribute() {}, querySelector: selector => parts[selector]};
  const list = {dataset: {}, scrollTop: 99,
    children: Array.from({length: 11}, () => ({hasAttribute: name => name === 'data-list-item'})),
    before(element) { this.toolbar = element; },
  };
  const document = {querySelector: () => null, getElementById: () => null,
    querySelectorAll: selector => selector === '[data-client-list]' ? [list] : [],
    createElement: () => toolbar,
    addEventListener(name, callback) { handlers.set(name, callback); },
  };
  vm.runInNewContext(source, {document, window: {addEventListener() {}}, location: {hash: ''}});
  assert.equal(toolbar.hidden, false);
  assert.equal(list.children[10].hidden, true);
  const added = {hasAttribute: name => name === 'data-list-item'};
  list.children.push(added);
  list.scrollTop = 99;
  list.refreshList(added);
  assert.equal(added.hidden, false);
  assert.equal(parts['[data-count]'].textContent, '11–12 of 12');
  assert.equal(parts['[data-page]'].textContent, 'Page 2 of 2');
  assert.equal(list.scrollTop, 99);
  list.children.splice(0, 10);
  list.refreshList();
  assert.equal(toolbar.hidden, true);
  assert.equal(parts['[data-count]'].textContent, '1–2 of 2');
  assert.equal(list.children.every(item => !item.hidden), true);
  assert.equal(list.scrollTop, 99);
});
