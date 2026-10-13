/* Read saved plans without navigating away from an unsaved editor. */
(() => {
  let mathReady;
  function loadMath() {
    if (window.katex) return Promise.resolve(window.katex);
    if (!mathReady) {
      mathReady = new Promise((resolve, reject) => {
        const style = document.createElement('link');
        style.rel = 'stylesheet';
        style.href = '/cms/static/katex/katex.min.css';
        document.head.append(style);
        const script = document.createElement('script');
        script.src = '/cms/static/katex/katex.min.js';
        script.onload = () => resolve(window.katex);
        script.onerror = () => { script.remove(); mathReady = null; reject(new Error('Could not load equation typesetting.')); };
        document.head.append(script);
      });
    }
    return mathReady;
  }

  async function typeset(root) {
    const equations = [...root.querySelectorAll('.plan-markdown .math')];
    if (!equations.length) return;
    const katex = await loadMath();
    equations.forEach(element => {
      if (element.dataset.typeset) return;
      katex.render(element.textContent.trim(), element, {
        displayMode: element.tagName === 'DIV', throwOnError: false, trust: false,
        output: 'htmlAndMathml', maxSize: 20,
      });
      element.dataset.typeset = 'true';
    });
  }

  function message(container, text, error = false) {
    const paragraph = document.createElement('p');
    if (error) paragraph.className = 'error';
    paragraph.textContent = text;
    container.append(paragraph);
  }

  const dialog = document.getElementById('plan-viewer');
  let controller;
  dialog?.addEventListener('close', () => controller?.abort());
  document.addEventListener('click', async event => {
    const link = event.target.closest('[data-plan-open]');
    if (!link || !dialog || typeof dialog.showModal !== 'function' || event.defaultPrevented ||
        event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    controller?.abort();
    const request = controller = new AbortController();
    const content = dialog.querySelector('[data-plan-content]');
    content.replaceChildren();
    content.setAttribute('aria-busy', 'true');
    message(content, 'Loading saved plan…');
    dialog.opener = link;
    dialog.showModal();
    try {
      const response = await fetch(link.href, {headers: {'HX-Request': 'true'}, signal: request.signal});
      if (!response.ok) throw new Error(response.status === 404 ? 'This entry no longer has an active plan.' : 'Could not load the saved plan. Try again.');
      const body = await response.text();
      if (request.signal.aborted) return;
      content.innerHTML = body;
      dialog.scrollTop = 0;
      try { await typeset(content); }
      catch { if (!request.signal.aborted) message(content, 'Equation typesetting could not load. The saved TeX is shown.', true); }
    } catch (error) {
      if (!request.signal.aborted) {
        content.replaceChildren();
        message(content, error.message || 'Could not load the saved plan. Try again.', true);
      }
    } finally {
      if (controller === request) content.removeAttribute('aria-busy');
    }
  });

  typeset(document).catch(() => {
    const plan = document.querySelector('.plan-document');
    if (plan) message(plan, 'Equation typesetting could not load. The saved TeX is shown.', true);
  });
})();
