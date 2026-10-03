/* Native form submission and Cancel links also work without JavaScript. */
(() => {
  const editors = () => [...document.querySelectorAll('form[data-editor], form[data-board-editor]')];
  const values = form => JSON.stringify([...form.querySelectorAll('input, textarea, select')]
    .filter(input => input.name && !['revision', 'snapshot'].includes(input.name))
    .map(input => [input.name, input.value]));
  const dirty = () => editors().some(form => form.dataset.dirty === 'true');
  let leaving = false;
  let refreshing = false;
  let logState = null;

  const header = document.querySelector('body > header');
  const updateHeaderHeight = () => {
    if (header) document.documentElement.style.setProperty('--cms-header-height', `${header.getBoundingClientRect().height}px`);
  };
  updateHeaderHeight();
  if (header && typeof ResizeObserver !== 'undefined') new ResizeObserver(updateHeaderHeight).observe(header);
  window.addEventListener('resize', updateHeaderHeight);

  function syncKind(form) {
    const kind = form.querySelector('select[name="kind"]')?.value;
    if (!kind) return;
    form.querySelectorAll('[data-kinds]').forEach(group => {
      const active = group.dataset.kinds.split(' ').includes(kind);
      group.hidden = !active;
      group.querySelectorAll('input, textarea, select').forEach(input => input.disabled = !active);
    });
  }

  function updateGeneratedId(form) {
    const preview = form.querySelector('[data-generated-id]');
    if (!preview) return;
    const name = form.querySelector('[name="name"]')?.value.trim() || '';
    const slug = name.replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^[-_]+|[-_]+$/g, '').toLowerCase();
    const kind = preview.dataset.kind;
    const prefix = {post: 'post', course: 'course', portfolio: 'portfolio', project: 'project', personal: 'personal'}[kind];
    const parent = form.querySelector('[data-course-select]')?.value || '';
    const generated = kind === 'chapter' ? (parent && slug ? `${parent}/${slug}` : '') : prefix && slug ? `${prefix}/${slug}` : '';
    preview.querySelector('code').textContent = generated || 'Enter a name to preview';

    const sections = form.querySelector('[data-section-select]');
    if (sections) {
      const course = form.querySelector('[data-course-select]')?.value || '';
      [...sections.options].forEach(option => {
        if (!option.dataset.courseId) return;
        const active = option.dataset.courseId === course;
        option.hidden = !active;
        option.disabled = !active;
      });
      if (sections.selectedOptions[0]?.disabled) sections.value = '';
    }
  }

  function sync() {
    const unsaved = dirty();
    editors().forEach(form => {
      if (form.hasAttribute('data-board-editor')) {
        const status = form.querySelector('[data-edit-status]');
        if (status) status.textContent = form.dataset.dirty === 'true' ? 'Unsaved changes' : '';
        return;
      }
      const editing = form.dataset.editing === 'true';
      const busy = form.dataset.busy === 'true';
      const fields = form.querySelector('[data-editor-fields]');
      if (fields) fields.disabled = !editing || busy;
      form.querySelectorAll('[data-begin-edit]').forEach(button => {
        button.hidden = editing;
        button.disabled = busy;
      });
      const save = form.querySelector('[data-save]');
      const cancel = form.querySelector('[data-cancel]');
      const status = form.querySelector('[data-edit-status]');
      if (save) { save.hidden = !editing; save.disabled = busy; }
      if (cancel) { cancel.hidden = !editing; cancel.setAttribute('aria-disabled', String(busy)); }
      if (status) status.textContent = busy ? 'Saving…' :
        form.dataset.dirty === 'true' ? 'Unsaved changes' : editing ? 'Editing' : 'Saved values';
    });
    const editorBusy = editors().some(form => form.dataset.busy === 'true');
    document.querySelectorAll('[data-publication-action]').forEach(button => {
      button.disabled = unsaved || editorBusy;
      button.title = unsaved ? 'Save or cancel your changes before changing publication state.' : '';
    });
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

  function initializeLists() {
    document.querySelectorAll('[data-client-list]').forEach(list => {
      if (list.dataset.paged) return;
      list.dataset.paged = 'true';
      const items = [...list.children].filter(item => item.hasAttribute('data-list-item'));
      if (items.length <= 10) return;
      let page = 1;
      let size = 10;
      const toolbar = document.createElement('nav');
      toolbar.className = 'pagination';
      toolbar.setAttribute('aria-label', (list.dataset.listLabel || 'Entries') + ' pages');
      toolbar.innerHTML = '<span data-count aria-live="polite"></span><button type="button" data-previous>Previous</button><span data-page></span><button type="button" data-next>Next</button><label class="page-choice">Per page <select aria-label="Entries per page"><option>10</option><option>25</option><option>50</option></select></label>';
      list.before(toolbar);
      const previous = toolbar.querySelector('[data-previous]');
      const next = toolbar.querySelector('[data-next]');
      function show() {
        const pages = Math.ceil(items.length / size);
        page = Math.min(page, pages);
        const start = (page - 1) * size;
        items.forEach((item, index) => item.hidden = index < start || index >= start + size);
        toolbar.querySelector('[data-count]').textContent = `${start + 1}–${Math.min(start + size, items.length)} of ${items.length}`;
        toolbar.querySelector('[data-page]').textContent = `Page ${page} of ${pages}`;
        previous.disabled = page === 1;
        next.disabled = page === pages;
        list.scrollTop = 0;
      }
      previous.addEventListener('click', () => { page--; show(); });
      next.addEventListener('click', () => { page++; show(); });
      toolbar.querySelector('select').addEventListener('change', event => { size = Number(event.target.value); page = 1; show(); });
      show();
    });
  }

  function closeDialog(dialog) {
    const form = dialog.querySelector('form[data-board-editor]');
    if (form?.dataset.dirty === 'true' && !window.confirm('Discard unsaved card changes?')) return;
    dialog.close();
  }

  function initializeDialogs() {
    document.querySelectorAll('dialog.cms-dialog').forEach(dialog => {
      if (!dialog.dataset.initialized) {
        dialog.dataset.initialized = 'true';
        dialog.querySelectorAll('button[data-dialog-close]').forEach(button => button.hidden = false);
        dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(dialog); });
        dialog.addEventListener('close', () => {
          const form = dialog.querySelector('form[data-board-editor]');
          if (form) {
            form.reset();
            form.removeAttribute('data-unsaved');
            form.dataset.dirty = 'false';
          }
          dialog.opener?.focus({preventScroll: true});
          sync();
        });
      }
      if (dialog.hasAttribute('data-auto-open')) {
        dialog.removeAttribute('data-auto-open');
        dialog.removeAttribute('open');
        dialog.showModal();
      }
    });
  }

  function initialize() {
    initializeLists();
    editors().forEach(form => {
      if (form.dataset.initialized) return;
      form.dataset.initialized = 'true';
      syncKind(form);
      form.savedValues = values(form);
      form.dataset.dirty = String(form.hasAttribute('data-board-editor') ? form.hasAttribute('data-unsaved') : !!form.closest('article')?.querySelector('.error'));
      updateGeneratedId(form);
    });
    initializeDialogs();
    sync();
  }

  function changed(event) {
    const form = event.target.closest('form[data-editor], form[data-board-editor]');
    if (!form) return;
    if (event.target.name === 'kind') syncKind(form);
    updateGeneratedId(form);
    form.dataset.dirty = String(values(form) !== form.savedValues || (form.hasAttribute('data-board-editor') ? form.hasAttribute('data-unsaved') : !!form.closest('article')?.querySelector('.error')));
    sync();
  }
  document.addEventListener('input', changed);
  document.addEventListener('change', changed);
  document.addEventListener('click', async event => {
    const dialogLink = event.target.closest('[data-dialog-open]');
    if (dialogLink && typeof HTMLDialogElement !== 'undefined') {
      const dialog = document.getElementById(dialogLink.dataset.dialogOpen);
      if (dialog) {
        event.preventDefault();
        dialog.opener = dialogLink;
        dialog.showModal();
        return;
      }
    }
    const dialogClose = event.target.closest('[data-dialog-close]');
    if (dialogClose && typeof HTMLDialogElement !== 'undefined') {
      const dialog = dialogClose.closest('dialog');
      if (dialog?.open) { event.preventDefault(); closeDialog(dialog); return; }
    }
    const anchor = event.target.closest('a[href^="#"]');
    if (anchor) {
      const target = document.getElementById(decodeURIComponent(anchor.getAttribute('href').slice(1)));
      if (target?.matches('details')) target.open = true;
    }
    const addLink = event.target.closest('[data-link-add]');
    if (addLink) {
      const form = addLink.closest('form');
      const picker = form.querySelector('[data-link-picker]');
      const field = form.querySelector('[name="artifact_ids"]');
      const values = new Set(field.value.split('\n').map(value => value.trim()).filter(Boolean));
      if (picker.value.trim()) values.add(picker.value.trim());
      field.value = [...values].join('\n');
      picker.value = '';
      field.dispatchEvent(new Event('input', {bubbles: true}));
    }
    const edit = event.target.closest('[data-begin-edit]');
    if (edit) {
      const form = edit.closest('form');
      form.dataset.editing = 'true';
      sync();
      (form.querySelector('summary') || form.querySelector('input:not([type="hidden"]), textarea, select'))?.focus({preventScroll: true});
    }
    const deletion = event.target.closest('[data-delete-link]');
    if (deletion && dirty()) {
      event.preventDefault();
      window.alert('Save or cancel your changes before reviewing deletion.');
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
    if (event.target.matches('form[data-publication-form]') && dirty()) {
      event.preventDefault();
      return;
    }
    if (event.target.matches('form[data-board-editor]')) leaving = !editors().some(form => form !== event.target && form.dataset.dirty === 'true');
    else if (!window.htmx && event.target.matches('form[data-editor]')) leaving = true;
  });
  document.addEventListener('htmx:beforeRequest', event => {
    const form = event.detail.elt.closest('form');
    if (form?.matches('[data-publication-form]')) {
      if (dirty()) { event.preventDefault(); return; }
      editors().forEach(editor => editor.dataset.busy = 'true');
    }
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
  function openHash() {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target?.matches('details')) target.open = true;
  }
  window.addEventListener('hashchange', openHash);
  initialize();
  openHash();
})();
