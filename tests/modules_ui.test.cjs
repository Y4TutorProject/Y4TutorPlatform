const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');

class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.events = {}; this.value = ''; this.dataset = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, callback) { this.events[event] = callback; }
  setAttribute(name, value) { this[name] = value; }
  focus() { this.focused = true; }
  reportValidity() { return true; }
}

function screen(admin = false, failure = false, eligible = true, applicationStatus = null, roles = ['student'], lecturer = false) {
  const nodes = new Map();
  const ids = admin ? ['tutor-applications', 'tutor-review-status', 'tutor-review-list', 'refresh-tutor-applications'] :
    ['module-search-form', 'programme-modules', 'module-search-status', 'open-tutor-applications',
      'close-tutor-applications', 'tutor-application-panel', 'tutor-module-query',
      'student-dashboard-title', 'student-dashboard-intro'];
  for (const id of ids) nodes.set(id, new Element());
  if (admin) {
    nodes.get('tutor-applications').dataset.collegeId = 'college';
    if (lecturer) nodes.get('tutor-applications').dataset.reviewPath = '/lecturers/me/tutor-applications';
  }
  else {
    nodes.get('module-search-form').elements = { q: { value: '' } };
    nodes.get('open-tutor-applications').hidden = true;
    nodes.get('tutor-application-panel').hidden = true;
    nodes.get('student-dashboard-title').textContent = 'Find your tutor';
    nodes.get('student-dashboard-intro').textContent = 'Welcome, student. Select a module to find your tutor.';
  }
  const calls = [];
  const redirects = [];
  const context = vm.createContext({
    document: { getElementById: id => nodes.get(id), createElement: tag => new Element(tag) },
    window: { location: { replace: url => redirects.push(url) } },
    encodeURIComponent,
    errorMessage: error => error.message,
    requestJSON: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/csrf')) return { csrf_token: 'token' };
      if (failure) throw Object.assign(new Error('Session expired'), { status: 401 });
      if (url.endsWith('/review')) return { application: { status: 'approved' } };
      if (url.endsWith('/tutor-applications')) return { applications: [{ id: 'application', username: '<script>', module_name: 'Databases', grade: 85 }] };
      if (url.endsWith('/tutor-application')) return { application: { status: 'pending' } };
      return { modules: [{ id: 'module', name: 'Encoded name', display_name: 'Computing & Informatics', roles, application_status: applicationStatus, can_apply_to_tutor: eligible }] };
    },
  });
  vm.runInContext(fs.readFileSync('frontend_shared/static/modules.js', 'utf8'), context);
  return { nodes, calls, redirects };
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('Student searches programme and submits a pending tutor application with CSRF', async () => {
  const { nodes, calls } = screen();
  await tick();
  const row = nodes.get('programme-modules').children[0];
  assert.equal(row.children[0].textContent, 'Computing & Informatics');
  assert.equal(row.children[1].textContent, 'Student');
  const form = row.children[2];
  assert.equal(form.children[1].type, 'number');
  assert.equal(form.children[1].min, '0');
  assert.equal(form.children[1].max, '100');
  assert.equal(form.children[1].required, true);
  form.children[1].value = '85.5';
  await form.events.submit({ preventDefault() {} });
  const submit = calls.find(call => call.options.method === 'POST');
  assert.equal(submit.url, '/api/lms/students/me/modules/module/tutor-application');
  assert.equal(submit.options.headers['X-CSRFToken'], 'token');
  assert.equal(JSON.parse(submit.options.body).grade, 85.5);
  assert.equal(form.children[3].textContent, 'Tutor application: pending');
  assert.equal(form.children[2].disabled, true);
  nodes.get('module-search-form').elements.q.value = 'Data & SQL';
  nodes.get('module-search-form').events.submit({ preventDefault() {} });
  await tick();
  assert(calls.some(call => call.url.endsWith('?q=Data%20%26%20SQL')));
});

test('Admin can approve pending module tutor applications', async () => {
  const { nodes, calls } = screen(true);
  await tick();
  const row = nodes.get('tutor-review-list').children[0];
  assert.equal(row.children[0].textContent, '<script> — Databases');
  assert.equal(row.children[1].textContent, 'Grade: 85/100');
  await row.children[2].events.click();
  const call = calls.find(call => call.url.endsWith('/review'));
  assert.equal(call.url, '/api/lms/college/college/tutor-applications/application/review');
  assert.equal(JSON.parse(call.options.body).decision, 'approved');
  assert.equal(row.children[4].textContent, 'Application approved.');
});

test('Expired search session returns to login and reports failure', async () => {
  const { nodes, redirects } = screen(false, true);
  await tick();
  assert.deepEqual(redirects, ['/login']);
  assert.equal(nodes.get('module-search-status').textContent, 'Session expired');
});


test('Same-year and future-year modules do not offer tutor application forms', async () => {
  const { nodes } = screen(false, false, false);
  await tick();
  assert.equal(nodes.get('programme-modules').children.length, 0);
  assert.match(nodes.get('module-search-status').textContent, /No eligible modules/);
  assert.equal(nodes.get('open-tutor-applications').hidden, true);
  assert.equal(nodes.get('tutor-application-panel').hidden, true);
});

test('Eligible students can open and close the applicable module list', async () => {
  const { nodes } = screen();
  await tick();
  const button = nodes.get('open-tutor-applications');
  const panel = nodes.get('tutor-application-panel');
  assert.equal(button.hidden, false);
  assert.equal(panel.hidden, true);
  button.events.click();
  assert.equal(panel.hidden, false);
  assert.equal(nodes.get('student-dashboard-title').textContent, 'Apply to be a Tutor');
  assert.match(nodes.get('student-dashboard-intro').textContent, /Choose an eligible module/);
  assert.equal(button['aria-expanded'], 'true');
  assert.equal(button.textContent, 'Close the apply menu');
  assert.equal(nodes.get('tutor-module-query').focused, true);
  assert.equal(nodes.get('programme-modules').children.length, 1);
  nodes.get('close-tutor-applications').events.click();
  assert.equal(panel.hidden, true);
  assert.equal(nodes.get('student-dashboard-title').textContent, 'Find your tutor');
  assert.equal(nodes.get('student-dashboard-intro').textContent, 'Welcome, student. Select a module to find your tutor.');
  assert.equal(button['aria-expanded'], 'false');
  assert.equal(button.focused, true);
  assert.equal(button.textContent, 'Apply to be a tutor');
  button.events.click();
  assert.equal(panel.hidden, false);
  button.events.click();
  assert.equal(panel.hidden, true);
  assert.equal(button.textContent, 'Apply to be a tutor');
  assert.equal(button['aria-expanded'], 'false');
  assert.equal(nodes.get('student-dashboard-title').textContent, 'Find your tutor');
});

test('Students with only existing applications or tutor memberships have no apply button', async () => {
  for (const [status, roles] of [['pending', ['student']], ['approved', ['tutor']], [null, ['tutor']]]) {
    const { nodes } = screen(false, false, true, status, roles);
    await tick();
    assert.equal(nodes.get('open-tutor-applications').hidden, true);
    assert.equal(nodes.get('programme-modules').children[0].children.some(child => child.tag === 'form'), false);
  }
});


test('Lecturer reviews use the current-user endpoint with CSRF', async () => {
  const { nodes, calls } = screen(true, false, true, null, [], true);
  await tick();
  const row = nodes.get('tutor-review-list').children[0];
  await row.children[2].events.click();
  const call = calls.find(call => call.url.endsWith('/review'));
  assert.equal(call.url, '/api/lms/lecturers/me/tutor-applications/application/review');
  assert.equal(call.options.headers['X-CSRFToken'], 'token');
});
