/* Native form submission and Cancel links also work without JavaScript. */
(() => {
  const editors = () => [...document.querySelectorAll('form[data-editor]')];
  const values = form => JSON.stringify([...form.querySelectorAll('input, textarea, select')]
    .filter(input => input.name && !['revision', 'snapshot'].includes(input.name))
    .map(input => [input.name, input.value]));
  const dirty = () => editors().some(form => form.dataset.dirty === 'true');
  let leaving = false;
  let refreshing = false;
  let logState = null;

  function syncKind(form) {
    const kind = form.querySelector('select[name="kind"]')?.value;
    if (!kind) return;
    form.querySelectorAll('[data-kinds]').forEach(group => {
      const active = group.dataset.kinds.split(' ').includes(kind);
      group.hidden = !active;
      group.querySelectorAll('input, textarea, select').forEach(input => input.disabled = !active);
    });
  }

  function sync() {
    const unsaved = dirty();
    editors().forEach(form => {
      const editing = form.dataset.editing === 'true';
      const busy = form.dataset.busy === 'true';
      const fields = form.querySelector('[data-editor-fields]');
      if (fields) fields.disabled = !editing || busy;
      form.querySelectorAll('[data-begin-edit]').forEach(button => {
        button.hidden = editing;
        button.disabled = busy;
      });
      form.querySelector('[data-save]').hidden = !editing;
      form.querySelector('[data-save]').disabled = busy;
      form.querySelector('[data-cancel]').hidden = !editing;
      form.querySelector('[data-cancel]').setAttribute('aria-disabled', String(busy));
      form.querySelector('[data-edit-status]').textContent = busy ? 'Saving…' :
        form.dataset.dirty === 'true' ? 'Unsaved changes' : editing ? 'Editing' : 'Saved values';
    });
    document.querySelectorAll('.publication-actions button').forEach(button => button.disabled = unsaved);
    const refresh = document.getElementById('refresh-preview');
    const buildStatus = document.getElementById('build-status')?.dataset.buildStatus;
    const building = ['queued', 'running'].includes(buildStatus);
    if (refresh) {
      const loading = refreshing || building;
      const failed = !loading && buildStatus === 'failed';
      refresh.disabled = unsaved || loading;
      refresh.dataset.refreshState = loading ? 'loading' : failed ? 'failed' : 'idle';
      refresh.setAttribute('aria-busy', String(loading));
      refresh.querySelector('[data-refresh-icon]').hidden = failed;
      refresh.querySelector('[data-refresh-error]').hidden = !failed;
      refresh.querySelector('[data-refresh-label]').textContent = loading ? 'Rebuilding…' : 'Rebuild';
      refresh.title = unsaved ? 'Save or cancel your changes before refreshing the preview.' :
        failed ? 'Rebuild failed. See the build logs, or click to retry.' : 'Build a preview from saved content';
    }
    const preview = document.querySelector('#build-status a');
    if (preview) document.getElementById('open-preview').href = preview.href;
  }

  function initialize() {
    editors().forEach(form => {
      if (form.dataset.initialized) return;
      form.dataset.initialized = 'true';
      syncKind(form);
      form.savedValues = values(form);
      form.dataset.dirty = String(!!form.closest('article')?.querySelector('.error'));
    });
    sync();
  }

  function changed(event) {
    const form = event.target.closest('form[data-editor]');
    if (!form) return;
    if (event.target.name === 'kind') syncKind(form);
    form.dataset.dirty = String(values(form) !== form.savedValues || !!form.closest('article')?.querySelector('.error'));
    sync();
  }
  document.addEventListener('input', changed);
  document.addEventListener('change', changed);
  document.addEventListener('click', async event => {
    const edit = event.target.closest('[data-begin-edit]');
    if (edit) {
      const form = edit.closest('form');
      form.dataset.editing = 'true';
      sync();
      form.querySelector('input:not([type="hidden"]), textarea, select')?.focus({preventScroll: true});
    }
    const cancel = event.target.closest('[data-cancel]');
    if (cancel) {
      if (cancel.getAttribute('aria-disabled') === 'true') event.preventDefault();
      else leaving = true;
    }
    const copy = event.target.closest('[data-copy]');
    if (copy) {
      try { await navigator.clipboard.writeText(copy.dataset.copy); copy.textContent = 'Copied'; }
      catch { window.prompt('Copy canonical source path', copy.dataset.copy); }
    }
  });
  window.addEventListener('beforeunload', event => {
    if (dirty() && !leaving) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('submit', event => {
    if (!window.htmx && event.target.matches('form[data-editor]')) leaving = true;
  });
  document.addEventListener('htmx:beforeRequest', event => {
    const form = event.detail.elt.closest('form');
    if (form?.matches('[data-editor]')) form.dataset.busy = 'true';
    if (form?.matches('[data-preview-refresh]')) refreshing = true;
    sync();
  });
  document.addEventListener('htmx:beforeSwap', event => {
    if (event.detail.target.id === 'build-status') {
      const logs = document.querySelector('#build-status .build-logs');
      if (logs) {
        const output = logs.querySelector('.build-output');
        logState = {
          id: logs.dataset.buildId,
          open: logs.open,
          scrollTop: output.scrollTop,
          scrollLeft: output.scrollLeft,
          followOutput: logs.open && output.scrollHeight - output.clientHeight - output.scrollTop <= 4,
          focused: document.activeElement === output ? '.build-output' :
            document.activeElement === logs.querySelector('summary') ? 'summary' : null
        };
      }
    }
    if ([400, 409, 412, 422, 428].includes(event.detail.xhr.status)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  document.addEventListener('htmx:beforeOnLoad', event => {
    if (event.detail.xhr.status < 400 && event.detail.xhr.getResponseHeader('HX-Redirect')) leaving = true;
  });
  document.addEventListener('htmx:afterSwap', event => {
    if (event.detail.target.id === 'build-status') {
      const logs = document.querySelector('#build-status .build-logs');
      if (logs) {
        const output = logs.querySelector('.build-output');
        if (logs.dataset.buildId === logState?.id) {
          logs.open = logState.open;
          output.scrollTop = logState.followOutput ? output.scrollHeight : logState.scrollTop;
          output.scrollLeft = logState.scrollLeft;
          if (logState.focused) logs.querySelector(logState.focused).focus({preventScroll: true});
        } else {
          output.scrollTop = output.scrollHeight;
        }
      }
    }
    initialize();
    if (event.detail.target.id !== 'build-status') {
      const error = document.querySelector('main .error');
      if (error) { error.tabIndex = -1; error.focus(); }
    }
  });
  document.addEventListener('htmx:afterRequest', event => {
    editors().forEach(form => form.dataset.busy = 'false');
    refreshing = false;
    if (event.detail.failed) {
      const form = event.detail.elt.closest('form[data-editor]');
      if (form?.isConnected) form.querySelector('[data-edit-status]').textContent = 'Could not save. Your changes are still here.';
      if (event.detail.elt.closest('form[data-preview-refresh]') || event.detail.elt.id === 'build-status') {
        const status = document.getElementById('build-status');
        status.dataset.buildStatus = 'failed';
        if (!status.querySelector('.error')) status.textContent = 'Could not rebuild the preview. Try again.';
      }
    }
    sync();
  });
  initialize();
})();
