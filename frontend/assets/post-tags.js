(function () {
  const controls = Array.from(document.querySelectorAll('[data-tag]'));
  const rows = Array.from(document.querySelectorAll('[data-post-tags]'));
  const sortButtons = Array.from(document.querySelectorAll('[data-sort]'));
  const table = document.querySelector('.posts-table tbody');
  const previous = document.getElementById('posts-previous');
  const next = document.getElementById('posts-next');
  let selectedTag = new URL(location.href).searchParams.get('tag') || '';
  let sortField = 'date', ascending = false, page = 0;
  const pageSize = 10;
  function render() {
    if (!table) return;
    const selected = selectedTag.toLocaleLowerCase();
    const filtered = rows.filter(row => selected === '' ||
      JSON.parse(row.dataset.postTags).some(tag => tag.toLocaleLowerCase() === selected));
    filtered.sort((a, b) => {
      let order = sortField === 'readingMinutes'
        ? Number(a.dataset[sortField]) - Number(b.dataset[sortField])
        : a.dataset[sortField].localeCompare(b.dataset[sortField]);
      if (order === 0) order = a.dataset.title.localeCompare(b.dataset.title);
      return ascending ? order : -order;
    });
    const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
    page = Math.min(page, pageCount - 1);
    rows.forEach(row => { row.hidden = true; });
    filtered.forEach((row, index) => {
      table.appendChild(row);
      row.hidden = index < page * pageSize || index >= (page + 1) * pageSize;
    });
    controls.forEach(button => button.setAttribute('aria-pressed',
      String(button.dataset.tag.toLocaleLowerCase() === selected)));
    sortButtons.forEach(button => button.closest('th').setAttribute('aria-sort',
      button.dataset.sort === sortField ? (ascending ? 'ascending' : 'descending') : 'none'));
    document.getElementById('posts-empty').hidden = filtered.length !== 0;
    document.getElementById('posts-page').textContent = filtered.length ? `${page + 1} / ${pageCount}` : '';
    previous.disabled = page === 0;
    next.disabled = page + 1 === pageCount;
  }
  controls.forEach(button => button.addEventListener('click', () => {
    selectedTag = button.dataset.tag;
    const url = new URL(location.href);
    if (selectedTag) url.searchParams.set('tag', selectedTag);
    else url.searchParams.delete('tag');
    history.replaceState(null, '', url);
    page = 0;
    render();
  }));
  sortButtons.forEach(button => button.addEventListener('click', () => {
    ascending = button.dataset.sort === sortField ? !ascending : true;
    sortField = button.dataset.sort;
    page = 0;
    render();
  }));
  if (previous) previous.addEventListener('click', () => { page -= 1; render(); });
  if (next) next.addEventListener('click', () => { page += 1; render(); });
  window.addEventListener('popstate', () => {
    selectedTag = new URL(location.href).searchParams.get('tag') || '';
    page = 0;
    render();
  });
  render();
})();
