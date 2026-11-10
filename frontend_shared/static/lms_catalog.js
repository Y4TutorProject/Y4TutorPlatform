"use strict";

function setupLMSCatalog() {
  const panel = document.getElementById('lms-imported-data');
  if (!panel) return;
  const status = document.getElementById('lms-catalog-status');
  const source = document.getElementById('lms-catalog-source');
  const browser = document.getElementById('lms-catalog-browser');
  const refresh = document.getElementById('refresh-lms-data');
  const type = document.getElementById('lms-catalog-type');
  const search = document.getElementById('lms-catalog-search');
  const previous = document.getElementById('lms-catalog-previous');
  const next = document.getElementById('lms-catalog-next');
  const pageStatus = document.getElementById('lms-catalog-page');
  let catalog, page = 0, requestNumber = 0;
  const pageSize = 25;
  const columns = {
    courses: ['Course / category', 'Code', 'Parent', 'Type', 'LMS ID'],
    modules: ['Module', 'Code', 'Course', 'Programme', 'Year', 'LMS ID'],
    users: ['Name', 'Username', 'Email', 'Current year', 'Status', 'LMS ID'],
    enrolments: ['User', 'Email', 'Course / module', 'Assigned roles'],
  };
  function node(tag, value) {
    const item = document.createElement(tag);
    item.textContent = value === undefined || value === null || value === '' ? '—' : String(value);
    return item;
  }
  function render() {
    if (!catalog) return;
    const courses = new Map((catalog.courses || []).map(c => [c.id, c]));
    const modules = new Map((catalog.modules || []).map(m => [m.id, m]));
    const users = new Map((catalog.users || []).map(u => [u.source_id, u]));
    const name = record => record ? record.name + (record.code ? ` (${record.code})` : '') : '';
    const userName = user => user ? [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || user.email || user.source_id : '';
    const formats = {
      courses: c => [c.name, c.code, name(courses.get(c.parent_id)), c.kind, c.source_id],
      modules: m => [m.name, m.code, name(courses.get(m.course_id)), name(courses.get(m.programme_id)), m.year, m.source_id],
      users: u => [userName(u), u.username, u.email, u.current_year, u.suspended ? 'Suspended' : 'Active', u.source_id],
      enrolments: e => {
        const user = users.get(e.user_source_id);
        const target = (e.target_type === 'module' ? modules : courses).get(e.target_id);
        return [userName(user) || e.user_source_id, user?.email,
          name(target) || e.target_id, (e.roles || ['student']).join(', ')];
      },
    };
    const query = search.value.trim().toLocaleLowerCase();
    const records = (catalog[type.value] || []).map(formats[type.value])
      .filter(row => row.some(value => String(value ?? '').toLocaleLowerCase().includes(query)));
    const pageCount = Math.max(1, Math.ceil(records.length / pageSize));
    page = Math.min(page, pageCount - 1);
    document.getElementById('lms-catalog-columns').replaceChildren(...columns[type.value].map(label => {
      const heading = node('th', label);
      heading.scope = 'col';
      return heading;
    }));
    const rows = records.slice(page * pageSize, (page + 1) * pageSize).map(record => {
      const row = document.createElement('tr');
      row.append(...record.map(value => node('td', value)));
      return row;
    });
    if (!rows.length) {
      const row = document.createElement('tr');
      const empty = node('td', query ? 'No imported records match your search.' : 'No imported records in this category.');
      empty.colSpan = columns[type.value].length;
      row.append(empty);
      rows.push(row);
    }
    document.getElementById('lms-catalog-rows').replaceChildren(...rows);
    document.getElementById('lms-catalog-caption').textContent = type.options[type.selectedIndex].textContent;
    pageStatus.textContent = `${records.length} record(s) · Page ${page + 1} of ${pageCount}`;
    previous.disabled = page === 0;
    next.disabled = page + 1 >= pageCount;
  }
  async function load() {
    const number = ++requestNumber;
    refresh.disabled = true;
    status.textContent = 'Loading imported data…';
    try {
      const { csrf_token } = await requestJSON('/api/users/auth/csrf');
      const result = await requestJSON(`/api/lms/college/${encodeURIComponent(panel.dataset.collegeId)}/lms/catalog`, {
        headers: { 'X-CSRFToken': csrf_token },
      });
      if (number !== requestNumber) return;
      catalog = result.catalog;
      const date = new Date(catalog.imported_at);
      const imported = Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString('en-IE', { timeZone: 'Europe/Dublin' });
      source.textContent = `${catalog.provider} · ${catalog.base_url} · Last imported: ${imported}`;
      status.textContent = `${catalog.courses.length} course(s)/category(s), ${catalog.modules.length} module(s), ${catalog.users.length} user(s), ${(catalog.enrolments || []).length} enrolment(s).`;
      if (catalog.enrolments_available === false) status.textContent += ' Enrolment data was not available in this import.';
      browser.hidden = false;
      page = 0;
      render();
    } catch (error) {
      if (number !== requestNumber) return;
      catalog = null;
      browser.hidden = true;
      source.textContent = '';
      if (error.status === 401) window.location.replace('/login');
      status.textContent = error.status === 404
        ? 'No imported data yet. Save an LMS connection and use Sync now to load your college data.'
        : errorMessage(error);
    } finally {
      if (number === requestNumber) refresh.disabled = false;
    }
  }
  type.addEventListener('change', () => { page = 0; render(); });
  search.addEventListener('input', () => { page = 0; render(); });
  previous.addEventListener('click', () => { if (page > 0) { page--; render(); } });
  next.addEventListener('click', () => { if (!next.disabled) { page++; render(); } });
  refresh.addEventListener('click', load);
  document.addEventListener('lms-catalog-updated', load);
  load();
}

setupLMSCatalog();
