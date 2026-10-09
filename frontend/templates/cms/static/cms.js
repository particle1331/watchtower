/* Native form submission and Cancel links also work without JavaScript. */
(() => {
  const editors = () => [...document.querySelectorAll('form[data-editor], form[data-board-editor], form[data-outline-form]')];
  const values = form => JSON.stringify([...form.querySelectorAll('input, textarea, select')]
    .filter(input => input.name && !['revision', 'snapshot'].includes(input.name))
    .map(input => [input.name, input.type === 'file' ? [...input.files].map(file => [file.name, file.size, file.lastModified]) : ['checkbox', 'radio'].includes(input.type) ? input.checked : input.multiple ? [...input.selectedOptions].map(option => option.value) : input.value]));
  const dirty = () => editors().some(form => form.dataset.dirty === 'true');
  let leaving = false;
  let refreshing = false;
  let logState = null;
  let pendingFiles = null;

  function initializeWorkspaceTabs() {
    document.querySelectorAll('[data-workspace-tabs]').forEach(nav => {
      if (nav.dataset.initialized) return;
      const links = [...nav.querySelectorAll('a[href^="#"]')];
      const panes = links.map(link => document.getElementById(link.hash.slice(1)));
      if (panes.some(pane => !pane)) return;
      nav.dataset.initialized = 'true';
      nav.setAttribute('role', 'tablist');
      function select(index, focus = false) {
        links.forEach((link, i) => {
          link.id = `${panes[i].id}-tab`;
          link.setAttribute('role', 'tab');
          link.setAttribute('aria-controls', panes[i].id);
          link.setAttribute('aria-selected', String(i === index));
          link.tabIndex = i === index ? 0 : -1;
          panes[i].setAttribute('role', 'tabpanel');
          panes[i].setAttribute('aria-labelledby', link.id);
          panes[i].hidden = i !== index;
        });
        if (focus) links[index].focus({preventScroll: true});
        nav.dataset.activePane = panes[index].id;
      }
      nav.selectPane = id => {
        const index = panes.findIndex(pane => pane.id === id);
        if (index >= 0) select(index);
      };
      links.forEach((link, index) => {
        link.addEventListener('click', event => {
          event.preventDefault();
          select(index);
          history.replaceState(null, '', link.hash);
        });
        link.addEventListener('keydown', event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? links.length - 1 :
            (index + (event.key === 'ArrowRight' ? 1 : -1) + links.length) % links.length;
          select(next, true);
          history.replaceState(null, '', links[next].hash);
        });
      });
      const hash = decodeURIComponent(location.hash.slice(1));
      const errorPane = panes.find(pane => pane.querySelector('.error'));
      const initial = errorPane?.id || (panes.some(pane => pane.id === hash) ? hash : nav.dataset.defaultPane);
      nav.selectPane(initial || panes[0].id);
    });
  }

  document.querySelectorAll('input[data-delete-id]').forEach(input => {
    const button = input.form?.querySelector('[data-delete-submit]');
    if (!button) return;
    const update = () => {
      button.disabled = input.value !== input.dataset.deleteId || button.dataset.deleteBlocked === 'true';
    };
    input.addEventListener('input', update);
    update();
  });

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
    const name = form.querySelector('[data-name-input]')?.value.trim() || form.querySelector('input[name=\'field:["title"]\']')?.value.trim() || '';
    const slug = name.replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^[-_]+|[-_]+$/g, '').toLowerCase();
    const kind = preview.dataset.kind;
    const prefix = {post: 'post', course: 'course', portfolio: 'portfolio', project: 'project', personal: 'personal'}[kind];
    const parent = form.querySelector('[data-course-select]')?.value || '';
    const generated = kind === 'chapter' ? (parent && slug ? `${parent}/${slug}` : '') : prefix && slug ? `${prefix}/${slug}` : '';
    preview.querySelector('code').textContent = generated || 'Enter a title to preview';

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
      const toolbar = form.id ? document.querySelector(`[data-editor-toolbar="${form.id}"]`) : null;
      [...form.querySelectorAll('[data-begin-edit]'), ...(toolbar?.querySelectorAll('[data-begin-edit]') || [])].forEach(button => {
        button.hidden = editing;
        button.disabled = busy;
      });
      const saves = [...form.querySelectorAll('[data-save]'), ...(toolbar?.querySelectorAll('[data-save]') || [])];
      const cancel = form.querySelector('[data-cancel]') || toolbar?.querySelector('[data-cancel]');
      const status = form.querySelector('[data-edit-status]');
      saves.forEach(save => { save.hidden = !editing; save.disabled = busy || save.hasAttribute('data-blocked'); });
      if (cancel) { cancel.hidden = !editing; cancel.setAttribute('aria-disabled', String(busy)); }
      if (status) status.textContent = busy ? 'Saving…' :
        form.dataset.dirty === 'true' ? 'Unsaved changes' : editing ? 'Editing' : 'Saved values';
    });
    const editorBusy = editors().some(form => form.dataset.busy === 'true');
    document.querySelectorAll('[data-publication-action]').forEach(button => {
      button.disabled = unsaved || editorBusy || button.hasAttribute('data-blocked');
      button.title = unsaved ? 'Save or cancel your changes before changing publication state.' : button.hasAttribute('data-blocked') ? 'Complete the core plan before starting' : '';
    });
    document.querySelectorAll('[data-summary-task]').forEach(button => {
      button.disabled = unsaved || editorBusy;
      const hint = button.closest('.summary-task')?.querySelector('[data-summary-task-hint]');
      if (hint) hint.textContent = unsaved ? 'Save your changes first so the task includes the latest brief.' :
        editorBusy ? 'Creating or saving…' : 'Creates a linked Kanban card with the saved brief and instructions for an agent.';
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
        if (dialog.hasAttribute('data-inline-dialog')) {
          dialog.removeAttribute('open');
          dialog.removeAttribute('data-inline-dialog');
        }
        dialog.querySelectorAll('button[data-dialog-close]').forEach(button => button.hidden = false);
        dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(dialog); });
        dialog.addEventListener('close', () => {
          const form = dialog.querySelector('form[data-board-editor]');
          if (form) {
            form.reset();
            form.removeAttribute('data-unsaved');
            form.dataset.dirty = 'false';
          }
          if (dialog.restorePane) {
            document.querySelectorAll('[data-workspace-tabs]').forEach(nav => nav.selectPane?.(dialog.restorePane));
            delete dialog.restorePane;
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

  let relationshipCounter = 0;
  function initializeRelationships() {
    document.querySelectorAll('[data-relationship]').forEach(picker => {
      if (picker.dataset.initialized) return;
      picker.dataset.initialized = 'true';
      const select = picker.querySelector('[data-relationship-select]');
      const enhanced = picker.querySelector('[data-relationship-enhanced]');
      const search = picker.querySelector('[data-relationship-search]');
      const results = picker.querySelector('[data-relationship-results]');
      const chips = picker.querySelector('[data-relationship-chips]');
      const status = picker.querySelector('[data-relationship-status]');
      const multiple = picker.dataset.multiple === 'true';
      const originalOptions = [...select.options];
      const listId = `relationship-results-${++relationshipCounter}`;
      results.id = listId;
      search.setAttribute('aria-controls', listId);
      select.closest('label').hidden = true;
      enhanced.hidden = false;
      let matches = [], active = -1, requestNumber = 0, timer, controller;
      const selected = () => [...select.selectedOptions].filter(option => option.value);
      function close() {
        results.hidden = true; search.setAttribute('aria-expanded', 'false');
        search.removeAttribute('aria-activedescendant'); active = -1;
      }
      function dismiss() {
        clearTimeout(timer); ++requestNumber; controller?.abort(); close(); status.textContent = '';
      }
      function renderChips() {
        chips.replaceChildren();
        selected().forEach(option => {
          const chip = document.createElement('span'); chip.className = 'relationship-chip';
          const label = document.createElement('span'); label.textContent = option.textContent;
          const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×';
          remove.setAttribute('aria-label', `Remove ${option.textContent}`);
          remove.addEventListener('click', () => {
            option.selected = false;
            if (!multiple) select.value = '';
            select.dispatchEvent(new Event('change', {bubbles: true}));
            renderChips(); dismiss(); search.focus();
          });
          chip.append(label, remove); chips.append(chip);
        });
      }
      function choose(index) {
        const item = matches[index]; if (!item) return;
        let option = [...select.options].find(option => option.value === item.id);
        if (!option) { option = new Option(`${item.title} · ${item.kind} · ${item.id} · ${item.lifecycle}`, item.id); select.add(option); }
        if (!multiple) [...select.options].forEach(option => option.selected = false);
        select.append(option); option.selected = true;
        search.value = ''; dismiss(); renderChips(); status.textContent = 'Content selected.';
        select.dispatchEvent(new Event('change', {bubbles: true})); search.focus();
      }
      function highlight() {
        [...results.children].forEach((option, index) => option.setAttribute('aria-selected', String(index === active)));
        if (active >= 0) {
          search.setAttribute('aria-activedescendant', `${listId}-${active}`);
          results.children[active]?.scrollIntoView({block: 'nearest'});
        } else search.removeAttribute('aria-activedescendant');
      }
      async function suggest() {
        const number = ++requestNumber;
        controller?.abort(); controller = new AbortController();
        status.textContent = 'Searching…';
        try {
          const response = await fetch(`/cms/lookup?q=${encodeURIComponent(search.value)}&kind=${encodeURIComponent(picker.dataset.kind || '')}&parent=${encodeURIComponent(picker.dataset.parent || '')}`, {signal: controller.signal});
          if (!response.ok) throw new Error('Search failed');
          const data = await response.json(); if (number !== requestNumber) return;
          const ids = new Set(selected().map(option => option.value));
          matches = data.artifacts.filter(item => !ids.has(item.id)); active = -1; results.replaceChildren();
          matches.forEach((item, index) => {
            const option = document.createElement('div'); option.id = `${listId}-${index}`;
            option.setAttribute('role', 'option'); option.setAttribute('aria-selected', 'false');
            option.textContent = `${item.title} · ${item.kind} · ${item.id} · ${item.lifecycle}`;
            option.addEventListener('mousedown', event => event.preventDefault());
            option.addEventListener('click', () => choose(index));
            results.append(option);
          });
          results.hidden = !matches.length; search.setAttribute('aria-expanded', String(!!matches.length));
          status.textContent = matches.length ? `${matches.length} suggestions. Use arrow keys and Enter to select.` : 'No matching content.';
        } catch (error) {
          if (error.name !== 'AbortError') { close(); status.textContent = 'Search unavailable. Reload or use the content selector.'; select.closest('label').hidden = false; }
        }
      }
      search.addEventListener('input', () => { dismiss(); timer = setTimeout(suggest, 150); });
      search.addEventListener('focus', suggest);
      search.addEventListener('click', () => { if (results.hidden) suggest(); });
      search.addEventListener('blur', dismiss);
      search.addEventListener('keydown', event => {
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); dismiss(); return; }
        if (event.key === 'Enter') { event.preventDefault(); if (!results.hidden && active >= 0) choose(active); return; }
        if (['ArrowDown', 'ArrowUp'].includes(event.key) && matches.length && !results.hidden) {
          event.preventDefault(); active = (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length; highlight();
        }
      });
      select.addEventListener('change', renderChips);
      select.form?.addEventListener('reset', () => setTimeout(() => {
        originalOptions.forEach(option => select.append(option)); search.value = ''; dismiss(); renderChips();
      }, 0));
      renderChips();
    });
  }

  function initialize() {
    initializeWorkspaceTabs();
    initializeRelationships();
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
    const form = event.target.closest('form[data-editor], form[data-board-editor], form[data-outline-form]');
    if (!form) return;
    if (event.target.name === 'kind') syncKind(form);
    updateGeneratedId(form);
    form.dataset.dirty = String(values(form) !== form.savedValues || (form.hasAttribute('data-board-editor') ? form.hasAttribute('data-unsaved') : !!form.closest('article')?.querySelector('.error')));
    sync();
  }
  document.addEventListener('input', changed);
  document.addEventListener('change', changed);
  document.addEventListener('invalid', event => {
    const pane = event.target.closest('[data-workspace-pane]');
    if (pane) document.querySelectorAll('[data-workspace-tabs]').forEach(nav => nav.selectPane?.(pane.id));
    const details = event.target.closest('details');
    if (details) details.open = true;
  }, true);
  document.addEventListener('change', event => {
    const select = event.target.closest('select[data-auto-submit]');
    if (select?.form) select.form.requestSubmit();
  });
  document.addEventListener('click', async event => {
    const dialogLink = event.target.closest('[data-dialog-open]');
    if (dialogLink && typeof HTMLDialogElement !== 'undefined') {
      const dialog = document.getElementById(dialogLink.dataset.dialogOpen);
      if (dialog) {
        event.preventDefault();
        const pane = dialog.closest('[data-workspace-pane]');
        if (pane?.hidden) {
          const tabs = [...document.querySelectorAll('[data-workspace-tabs]')].find(nav => [...nav.querySelectorAll('a[href^="#"]')].some(link => link.hash === `#${pane.id}`));
          if (tabs) {
            dialog.restorePane = tabs.dataset.activePane;
            tabs.selectPane?.(pane.id);
          }
        }
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
      const form = edit.form || edit.closest('form');
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
      try {
        await navigator.clipboard.writeText(copy.dataset.copy);
        const originalLabel = copy.dataset.copyLabel || copy.getAttribute('aria-label') || copy.textContent.trim() || 'Copy';
        copy.dataset.copyLabel = originalLabel;
        copy.setAttribute('aria-label', 'Copied');
        copy.setAttribute('title', 'Copied');
        copy.classList.add('is-copied');
        window.clearTimeout(copy.copyResetTimer);
        copy.copyResetTimer = window.setTimeout(() => {
          copy.setAttribute('aria-label', originalLabel);
          copy.setAttribute('title', originalLabel);
          copy.classList.remove('is-copied');
        }, 1400);
      }
      catch { window.prompt('Copy canonical source path', copy.dataset.copy); }
    }
  });
  window.addEventListener('beforeunload', event => {
    if (dirty() && !leaving) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('submit', event => {
    if (event.target.matches('form[data-publication-form], form[data-summary-task-form]') && dirty()) {
      event.preventDefault();
      return;
    }
    if (event.target.matches('form[data-outline-form]')) {
      if (editors().some(form => form !== event.target && form.dataset.dirty === 'true')) {
        event.preventDefault(); window.alert('Save or cancel your other changes before changing the outline.'); return;
      }
      leaving = true;
    }
    if (event.target.matches('form[data-board-editor]')) leaving = !editors().some(form => form !== event.target && form.dataset.dirty === 'true');
    else if (!window.htmx && event.target.matches('form[data-editor]')) leaving = true;
  });
  document.addEventListener('htmx:beforeRequest', event => {
    const form = event.detail.elt.closest('form');
    if (form?.matches('[data-publication-form], [data-summary-task-form]')) {
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
      pendingFiles = [...event.detail.target.querySelectorAll('input[type="file"]')]
        .filter(input => input.files.length).map(input => ({name: input.name, files: input.files}));
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
    if (pendingFiles) {
      const form = document.querySelector('#unsaved-card form, #artifact-editor-form, #new-editor-form');
      pendingFiles.forEach(({name, files}) => {
        const input = form?.querySelector(`input[type="file"][name="${name}"]`);
        if (input) input.files = files;
      });
      pendingFiles = null;
      sync();
    }
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
    const pane = target?.closest('[data-workspace-pane]');
    if (pane) document.querySelectorAll('[data-workspace-tabs]').forEach(nav => nav.selectPane?.(pane.id));
    if (target?.matches('details')) target.open = true;
  }
  window.addEventListener('hashchange', openHash);
  initialize();
  openHash();
})();
