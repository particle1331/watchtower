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
      if (hint) hint.textContent = unsaved ? 'Save your changes first so the task can read the latest content context.' :
        editorBusy ? 'Creating or saving…' : 'Creates a linked execution task with instructions to read the content’s current source and internal notes.';
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
      const items = () => [...list.children].filter(item => item.hasAttribute('data-list-item'));
      let page = 1;
      let size = 10;
      const toolbar = document.createElement('nav');
      toolbar.className = 'pagination';
      toolbar.setAttribute('aria-label', (list.dataset.listLabel || 'Entries') + ' pages');
      toolbar.innerHTML = '<span data-count aria-live="polite"></span><button type="button" data-previous>Previous</button><span data-page></span><button type="button" data-next>Next</button><label class="page-choice">Per page <select aria-label="Entries per page"><option>10</option><option>25</option><option>50</option></select></label>';
      list.before(toolbar);
      const previous = toolbar.querySelector('[data-previous]');
      const next = toolbar.querySelector('[data-next]');
      function show(resetScroll = true) {
        const current = items();
        const pages = Math.max(1, Math.ceil(current.length / size));
        page = Math.min(page, pages);
        const start = (page - 1) * size;
        current.forEach((item, index) => item.hidden = index < start || index >= start + size);
        toolbar.hidden = current.length <= 10;
        toolbar.querySelector('[data-count]').textContent = `${current.length ? start + 1 : 0}–${Math.min(start + size, current.length)} of ${current.length}`;
        toolbar.querySelector('[data-page]').textContent = `Page ${page} of ${pages}`;
        previous.disabled = page === 1;
        next.disabled = page === pages;
        if (resetScroll) list.scrollTop = 0;
      }
      list.refreshList = revealed => {
        const index = items().indexOf(revealed);
        if (index >= 0) page = Math.floor(index / size) + 1;
        show(false);
      };
      previous.addEventListener('click', () => { page--; show(); });
      next.addEventListener('click', () => { page++; show(); });
      toolbar.querySelector('select').addEventListener('change', event => { size = Number(event.target.value); page = 1; show(); });
      show();
    });
  }

  function closeDialog(dialog) {
    const form = dialog.querySelector('form[data-board-editor]');
    if (form?.dataset.dirty === 'true' && !window.confirm('Discard unsaved card changes?')) return false;
    dialog.close();
    return true;
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

  function initializeTodos() {
    document.querySelectorAll('[data-todo-editor]').forEach(editor => {
      if (editor.dataset.initialized) return;
      editor.dataset.initialized = 'true';
      const list = editor.querySelector('[data-todo-list]');
      const input = editor.querySelector('[data-todo-new]');
      const add = editor.querySelector('[data-todo-add]');
      const rows = () => [...list.querySelectorAll('[data-todo-row]')];
      function update() {
        const items = rows();
        items.forEach((row, index) => {
          row.querySelector('[data-todo-done]').value = String(index);
          row.querySelector('[data-todo-discard]').value = String(index);
        });
        editor.querySelector('[data-todo-count]').textContent = `${items.filter(row => row.querySelector('[data-todo-done]').checked).length}/${items.length}`;
        editor.querySelector('[data-todo-empty]').hidden = items.length > 0;
      }
      function bind(row) {
        const remove = row.querySelector('[data-todo-remove]');
        remove.hidden = false;
        row.querySelector('[data-todo-remove-fallback]').hidden = true;
        remove.addEventListener('click', () => {
          row.remove();
          update();
          list.dispatchEvent(new Event('input', {bubbles: true}));
          input.focus();
        });
        row.querySelector('[data-todo-done]').addEventListener('change', update);
      }
      function append() {
        const text = input.value.trim();
        if (!text) { input.focus(); return; }
        const row = editor.querySelector('[data-todo-template]').content.firstElementChild.cloneNode(true);
        row.querySelector('[data-todo-text]').value = text;
        bind(row);
        list.append(row);
        input.value = '';
        update();
        list.dispatchEvent(new Event('input', {bubbles: true}));
        input.focus();
      }
      rows().forEach(bind);
      add.hidden = false;
      add.addEventListener('click', append);
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); append(); }
      });
      update();
    });
  }

  function initializeKanbanDragDrop() {
    document.querySelectorAll('[data-kanban-board]').forEach(board => {
      if (board.dataset.dragInitialized) return;
      board.dataset.dragInitialized = 'true';
      let dragged = null;
      let blocked = false;
      let saving = false;
      let needsReload = false;
      const columns = [...board.querySelectorAll('[data-kanban-column]')];
      const status = board.querySelector('[data-kanban-move-status]');
      const reload = board.querySelector('[data-kanban-reload]');
      const refreshColumn = (column, revealed) => {
        column.querySelector('[data-kanban-count]').textContent = column.querySelectorAll('[data-kanban-card]').length;
        const list = column.querySelector('[data-client-list]');
        list.querySelector('[data-kanban-empty]').hidden = !!list.querySelector('[data-kanban-card]');
        list.refreshList?.(revealed);
      };
      async function moveCard(card, column) {
        if (!card || !column || saving || needsReload) return;
        if (dirty()) { window.alert('Save or cancel your changes before moving a card.'); return; }
        const origin = card.closest('[data-kanban-column]');
        if (origin === column) return;
        const id = card.dataset.kanbanCard;
        const view = document.getElementById(`view-${id}`);
        const form = view?.querySelector('form[data-kanban-move]');
        const revision = form?.querySelector('input[name="revision"]')?.value;
        if (!revision) return;
        const originalList = card.parentElement;
        const nextSibling = card.nextSibling;
        const list = column.querySelector('[data-client-list]');
        const before = [...list.querySelectorAll('[data-kanban-card]')].find(item => Number(item.dataset.kanbanOrder) > Number(card.dataset.kanbanOrder));
        const controls = [...board.querySelectorAll('form input, form textarea, form select, form button')].map(control => [control, control.disabled]);
        const label = column.getAttribute('aria-label');
        saving = true;
        board.dataset.moving = 'true';
        controls.forEach(([control]) => control.disabled = true);
        card.classList.add('is-saving');
        list.insertBefore(card, before || null);
        refreshColumn(origin);
        refreshColumn(column, card);
        status.hidden = false;
        status.textContent = `Saving move to ${label}…`;
        try {
          const response = await fetch(`/api/kanban/${encodeURIComponent(id)}`, {
            method: 'PATCH', headers: {'Content-Type': 'application/json', 'If-Match': revision},
            body: JSON.stringify({column: column.dataset.kanbanColumn}),
          });
          const result = await response.json();
          if (!response.ok || !result.board_revision) {
            throw new Error(response.status === 412 ? 'The board changed. Reload the saved board before moving again.' : result.error?.message || 'The save could not be confirmed. Reload the saved board.');
          }
          board.querySelectorAll('input[name="revision"]').forEach(input => input.value = result.board_revision);
          const edit = document.getElementById(`edit-${id}`)?.querySelector('form[data-board-editor]');
          [form, edit].filter(Boolean).forEach(editor => {
            const select = editor.querySelector('select[name="column"]');
            select.value = column.dataset.kanbanColumn;
            [...select.options].forEach(option => option.defaultSelected = option.value === select.value);
            if (editor === edit) editor.savedValues = values(editor);
          });
          view.querySelector('[data-kanban-card-column]').textContent = label;
          status.textContent = `Moved to ${label}.`;
        } catch (error) {
          originalList.insertBefore(card, nextSibling?.parentNode === originalList ? nextSibling : null);
          refreshColumn(origin, card);
          refreshColumn(column);
          needsReload = true;
          reload.hidden = false;
          status.textContent = `Move to ${label} was not confirmed. ${error.message || 'Reload the saved board before moving again.'}`;
        } finally {
          saving = false;
          delete board.dataset.moving;
          controls.forEach(([control, disabled]) => control.disabled = disabled);
          card.classList.remove('is-saving');
        }
      }
      const clearTargets = () => columns.forEach(column => column.classList.remove('is-drop-target'));
      const finish = () => {
        dragged?.classList.remove('is-dragging');
        dragged = null;
        clearTargets();
      };
      board.querySelectorAll('[data-kanban-card]').forEach(card => {
        card.draggable = true;
        card.querySelectorAll('a').forEach(link => link.draggable = false);
      });
      const hint = board.querySelector('[data-kanban-drag-hint]');
      if (hint) hint.hidden = false;
      board.addEventListener('pointerdown', event => {
        blocked = !!event.target.closest('button, input, textarea, select, .kanban-card-footer');
      });
      board.addEventListener('dragstart', event => {
        const card = event.target.closest('[data-kanban-card]');
        if (!card) return;
        if (blocked || saving || needsReload || !event.dataTransfer) { event.preventDefault(); return; }
        if (dirty()) {
          event.preventDefault();
          window.alert('Save or cancel your changes before moving a card.');
          return;
        }
        dragged = card;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', card.dataset.kanbanCard);
        card.classList.add('is-dragging');
      });
      board.addEventListener('dragover', event => {
        const column = event.target.closest('[data-kanban-column]');
        if (!dragged || !columns.includes(column)) return;
        event.preventDefault();
        clearTargets();
        const sameColumn = column === dragged.closest('[data-kanban-column]');
        if (event.dataTransfer) event.dataTransfer.dropEffect = sameColumn ? 'none' : 'move';
        if (!sameColumn) column.classList.add('is-drop-target');
      });
      board.addEventListener('dragleave', event => {
        const column = event.target.closest('[data-kanban-column]');
        if (column && !column.contains(event.relatedTarget)) column.classList.remove('is-drop-target');
      });
      board.addEventListener('drop', event => {
        const column = event.target.closest('[data-kanban-column]');
        if (!dragged || !columns.includes(column)) return;
        event.preventDefault();
        const card = dragged;
        finish();
        return moveCard(card, column);
      });
      board.addEventListener('dragend', finish);
      board.addEventListener('submit', event => {
        if (!event.target.matches('form[data-kanban-move]')) return;
        event.preventDefault();
        const id = event.target.querySelector('input[name="card_id"]').value;
        const destination = event.target.querySelector('select[name="column"]').value;
        const card = [...board.querySelectorAll('[data-kanban-card]')].find(item => item.dataset.kanbanCard === id);
        return moveCard(card, columns.find(column => column.dataset.kanbanColumn === destination));
      });
    });
  }

  function initialize() {
    initializeWorkspaceTabs();
    initializeRelationships();
    initializeLists();
    initializeTodos();
    initializeKanbanDragDrop();
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
    const dialog = event.target.closest('dialog.cms-dialog');
    if (dialog && !dialog.open && typeof dialog.showModal === 'function') dialog.showModal();
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
        const previousDialog = dialogLink.closest('dialog');
        const opener = previousDialog?.opener || dialogLink;
        if (previousDialog?.open && previousDialog !== dialog && !previousDialog.contains(dialog)) {
          if (!closeDialog(previousDialog)) return;
          dialog.opener = opener;
        } else {
          dialog.opener = dialogLink;
        }
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
    if (event.target.matches('form[data-kanban-move]')) {
      if (event.defaultPrevented) return;
      if (dirty()) {
        event.preventDefault();
        window.alert('Save or cancel your changes before moving a card.');
        return;
      }
      leaving = true;
    }
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
