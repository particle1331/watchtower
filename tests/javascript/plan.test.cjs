const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/templates/cms/static/plan.js', 'utf8');

function environment({status = 200, body = '<article>Saved plan</article>', equations = [], native = true, fetcher} = {}) {
  const handlers = {}, requests = [], rendered = [];
  const content = {
    children: [], attrs: {}, innerHTML: '',
    append(node) { this.children.push(node); },
    replaceChildren() { this.children = []; this.innerHTML = ''; },
    setAttribute(name, value) { this.attrs[name] = value; },
    removeAttribute(name) { delete this.attrs[name]; },
    querySelectorAll() { return equations; },
  };
  const dialog = {
    open: false, listeners: {}, querySelector: () => content,
    addEventListener(name, callback) { this.listeners[name] = callback; },
    ...(native ? {showModal() { this.open = true; }} : {}),
    close() { this.open = false; this.listeners.close(); },
  };
  const link = {href: '/cms/plan/post/example'};
  const editor = {value: 'Unsaved content', dataset: {dirty: 'true'}, uploads: ['selected.png']};
  const document = {
    getElementById: () => dialog, querySelectorAll: () => [], querySelector: () => null,
    addEventListener(name, callback) { handlers[name] = callback; },
    createElement: () => ({}),
  };
  const window = {katex: {render(tex, element, options) { rendered.push({tex, options}); }}};
  vm.runInNewContext(source, {document, window, AbortController, fetch: async (url, options) => {
    requests.push({url, options});
    return fetcher ? fetcher(url, options) : {ok: status === 200, status, text: async () => body};
  }});
  async function click(extra = {}) {
    const event = {target: {closest: () => link}, button: 0, preventDefault() { this.defaultPrevented = true; }, ...extra};
    await handlers.click(event);
    return event;
  }
  return {dialog, content, link, editor, requests, rendered, click};
}

test('opens a saved reader with a GET and preserves dirty fields and uploads', async () => {
  const env = environment();
  const event = await env.click();
  assert.equal(event.defaultPrevented, true);
  assert.equal(env.dialog.open, true);
  assert.equal(env.dialog.opener, env.link);
  assert.equal(env.requests.length, 1);
  assert.equal(env.requests[0].options.method, undefined);
  assert.equal(env.requests[0].options.headers['HX-Request'], 'true');
  assert.equal(env.content.innerHTML, '<article>Saved plan</article>');
  assert.equal(env.content.attrs['aria-busy'], undefined);
  assert.equal(env.editor.value, 'Unsaved content');
  assert.equal(env.editor.dataset.dirty, 'true');
  assert.deepEqual(env.editor.uploads, ['selected.png']);
  env.dialog.close();
  assert.equal(env.requests[0].options.signal.aborted, true);
});

test('typesets inline and display math without enabling trusted HTML commands', async () => {
  const equations = [{tagName: 'SPAN', textContent: '\\alpha_i', dataset: {}},
    {tagName: 'DIV', textContent: '\\frac{a}{b}', dataset: {}}];
  const env = environment({equations});
  await env.click();
  assert.equal(env.rendered.length, 2);
  assert.deepEqual(env.rendered.map(item => item.options.displayMode), [false, true]);
  assert.ok(env.rendered.every(item => item.options.trust === false && item.options.throwOnError === false));
  assert.ok(equations.every(element => element.dataset.typeset === 'true'));
});

test('unavailable plans show a useful message and leave the editor intact', async () => {
  const env = environment({status: 404});
  await env.click();
  assert.equal(env.content.children[0].textContent, 'This entry no longer has an active plan.');
  assert.equal(env.editor.dataset.dirty, 'true');
});

test('closing while loading prevents the response from changing the reader', async () => {
  let finish;
  const env = environment({fetcher: () => new Promise(resolve => finish = resolve)});
  const pending = env.click();
  env.dialog.close();
  finish({ok: true, text: async () => '<article>Late response</article>'});
  await pending;
  assert.equal(env.content.innerHTML, '');
});

test('ordinary links remain usable without dialogs and modified clicks retain native behavior', async () => {
  const fallback = environment({native: false});
  assert.equal((await fallback.click()).defaultPrevented, undefined);
  assert.equal(fallback.requests.length, 0);
  const modified = environment();
  assert.equal((await modified.click({ctrlKey: true})).defaultPrevented, undefined);
  assert.equal(modified.requests.length, 0);
});
