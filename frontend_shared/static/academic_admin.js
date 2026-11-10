"use strict";

async function setupAcademicManagement() {
  const panel = document.getElementById('academic-management');
  if (!panel) return;
  const base = `/api/colleges/college/${encodeURIComponent(panel.dataset.collegeId)}/academic`;
  const status = document.getElementById('academic-status');
  const courseForm = document.getElementById('create-course-form');
  const moduleForm = document.getElementById('create-module-form');
  const assignmentForm = document.getElementById('assign-academic-user-form');
  const refresh = document.getElementById('refresh-academics');
  const forms = [courseForm, moduleForm, assignmentForm];
  let records, users, busy = false;
  function node(tag, text, className = '') {
    const item = document.createElement(tag);
    item.textContent = text;
    item.className = className;
    return item;
  }
  async function call(path = '', method = 'GET', data) {
    const { csrf_token } = await requestJSON('/api/users/auth/csrf');
    return requestJSON(base + path, {
      method, headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf_token },
      ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    });
  }
  function failed(target, error) {
    target.textContent = errorMessage(error);
    if (error.status === 401) window.location.replace('/login');
  }
  function options(select, entries, placeholder) {
    const old = select.value;
    const items = [["", placeholder], ...entries].map(([value, label]) => {
      const option = node('option', label);
      option.value = value;
      return option;
    });
    select.replaceChildren(...items);
    select.value = entries.some(([value]) => value === old) ? old : '';
  }
  function updateAssignmentFields() {
    const course = assignmentForm.elements.target.value.startsWith('course:');
    assignmentForm.elements.year.disabled = !course;
    assignmentForm.elements.year.required = course;
    assignmentForm.elements.role.options[1].disabled = course;
    if (course) assignmentForm.elements.role.value = 'student';
  }
  function enableForms() {
    courseForm.querySelector('button[type=submit]').disabled = busy || !records;
    moduleForm.querySelector('button[type=submit]').disabled = busy || !records?.courses.length;
    assignmentForm.querySelector('button[type=submit]').disabled = busy || !users?.length || !records?.courses.length;
    refresh.disabled = busy;
  }
  function render() {
    const courses = new Map(records.courses.map(course => [course.id, course]));
    const modules = new Map(records.modules.map(module => [module.id, module]));
    const names = new Map(users.map(user => [user.id, `${user.username} (${user.email})`]));
    const directory = records.directory_users || [];
    const directoryNames = new Map(directory.map(user => [user.email,
      `${user.username || [user.first_name, user.last_name].filter(Boolean).join(' ') || 'User'} (${user.email})`]));
    const label = record => record.name + (record.code ? ` (${record.code})` : '');
    const moduleLabel = module => `${label(courses.get(module.course_id))} — Year ${module.year} — ${label(module)}`;
    options(moduleForm.elements.course_id, records.courses.map(c => [c.id, label(c)]), 'Choose a course');
    options(assignmentForm.elements.user_id, users.map(u => [u.id, names.get(u.id)]), 'Choose a user');
    options(assignmentForm.elements.target, [
      ...records.courses.map(c => [`course:${c.id}`, `Course: ${label(c)}`]),
      ...records.modules.map(m => [`module:${m.id}`, `Module: ${moduleLabel(m)}`]),
    ], 'Choose a course or module');
    updateAssignmentFields();
    const catalog = document.getElementById('academic-catalog-list');
    catalog.replaceChildren();
    for (const course of records.courses) {
      const row = node('li', '', 'list-group-item');
      row.append(node('h4', label(course), 'h6'));
      const list = node('ul', '');
      const children = records.modules.filter(m => m.course_id === course.id).sort((a, b) => a.year - b.year || a.name.localeCompare(b.name));
      for (const module of children) list.append(node('li', `Year ${module.year}: ${label(module)}`));
      row.append(children.length ? list : node('p', 'No modules yet.', 'mb-0 text-muted'));
      catalog.append(row);
    }
    if (!records.courses.length) catalog.append(node('li', 'No courses yet. Create your first course above.', 'list-group-item'));
    const assignments = document.getElementById('academic-assignment-list');
    assignments.replaceChildren();
    for (const assignment of records.assignments) {
      const target = assignment.target_type === 'course' ? `${label(courses.get(assignment.target_id))} — Year ${assignment.year}` : moduleLabel(modules.get(assignment.target_id));
      const row = node('li', '', 'list-group-item d-flex justify-content-between align-items-center gap-3');
      row.append(node('span', `${names.get(assignment.user_id) || directoryNames.get(assignment.user_email) || assignment.user_email || 'Unavailable user'} · ${assignment.role} · ${target}`));
      const remove = node('button', 'Remove assignment', 'btn btn-sm btn-outline-danger');
      remove.type = 'button';
      remove.addEventListener('click', async () => {
        if (busy) return;
        busy = true;
        remove.disabled = true;
        enableForms();
        try { await call(`/assignments/${encodeURIComponent(assignment.id)}`, 'DELETE'); await load(); }
        catch (error) { failed(status, error); remove.disabled = false; }
        finally { busy = false; enableForms(); }
      });
      row.append(remove);
      assignments.append(row);
    }
    if (!records.assignments.length) assignments.append(node('li', 'No user assignments yet.', 'list-group-item'));
    const directoryList = document.getElementById('academic-directory-list');
    directoryList.replaceChildren(...directory.map(user => node('li',
      `${directoryNames.get(user.email)} · ${user.user_id ? 'Linked account' : 'Awaiting registration'}`, 'list-group-item')));
    if (!directory.length) directoryList.append(node('li', 'No CSV directory users yet.', 'list-group-item'));
    status.textContent = `${records.courses.length} course(s), ${records.modules.length} module(s), ${records.assignments.length} assignment(s).`;
  }
  async function load() {
    const [catalog, directory] = await Promise.all([
      call(), requestJSON(`/api/users/college/${encodeURIComponent(panel.dataset.collegeId)}/users`),
    ]);
    records = catalog;
    users = directory.users.filter(user => user.roles.some(role => ['student', 'tutor'].includes(role)));
    render();
  }
  function submit(form, path, statusId, payload) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (busy || !form.reportValidity()) return;
      const feedback = document.getElementById(statusId);
      busy = true;
      enableForms();
      feedback.textContent = 'Saving…';
      try {
        await call(path, 'POST', payload(form.elements));
        feedback.textContent = 'Saved successfully.';
        form.reset();
        await load();
      } catch (error) { failed(feedback, error); }
      finally { busy = false; enableForms(); }
    });
  }
  submit(courseForm, '/courses', 'course-save-status', f => ({ name: f.name.value.trim(), code: f.code.value.trim() }));
  submit(moduleForm, '/modules', 'module-save-status', f => ({ name: f.name.value.trim(), code: f.code.value.trim(), course_id: f.course_id.value, year: Number(f.year.value) }));
  submit(assignmentForm, '/assignments', 'assignment-save-status', f => {
    const [target_type, target_id] = f.target.value.split(':');
    return { user_id: f.user_id.value, target_type, target_id, role: f.role.value,
      ...(target_type === 'course' ? { year: Number(f.year.value) } : {}) };
  });
  assignmentForm.elements.target.addEventListener('change', updateAssignmentFields);
  refresh.addEventListener('click', async () => {
    if (busy) return;
    busy = true;
    enableForms();
    try { await load(); } catch (error) { failed(status, error); }
    finally { busy = false; enableForms(); }
  });
  document.addEventListener('academic-data-updated', () => refresh.click());
  busy = true;
  enableForms();
  try { await load(); } catch (error) { failed(status, error); }
  finally { busy = false; enableForms(); }
}

setupAcademicManagement();
