const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor(tag = '') { this.tag = tag; this.children = []; this.events = {}; this.value = ''; this.dataset = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, callback) { this.events[name] = callback; }
  reportValidity() { return true; }
  reset() { for (const field of Object.values(this.elements)) field.value = ''; }
  get options() { return this.children; }
  querySelector() { return this.submit; }
}

function screen() {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  node('academic-management').dataset.collegeId = 'college';
  for (const [id, fields] of [
    ['create-course-form', ['name', 'code']],
    ['create-module-form', ['name', 'code', 'course_id', 'year']],
    ['assign-academic-user-form', ['user_id', 'target', 'role', 'year']],
  ]) {
    node(id).elements = Object.fromEntries(fields.map(field => [field, new Element()]));
    node(id).submit = new Element('button');
  }
  node('assign-academic-user-form').elements.role.children = [new Element('option'), new Element('option')];
  const records = {
    courses: [{ id: 'course', name: 'Computing <script>', code: 'COMP' }],
    modules: [{ id: 'module', name: 'Databases', code: 'DB', course_id: 'course', year: 2 }],
    assignments: [],
  };
  const calls = [], redirects = [];
  let failure = null;
  const context = vm.createContext({
    document: { getElementById: node, createElement: tag => new Element(tag) },
    window: { location: { replace: url => redirects.push(url) } },
    errorMessage: error => error.message,
    requestJSON: async (url, options = {}) => {
      calls.push({ url, options });
      if (failure) throw failure;
      if (url.endsWith('/auth/csrf')) return { csrf_token: 'token' };
      if (url.endsWith('/users')) return { users: [{ id: 'user', username: '<Student>', email: 'student@college.test', roles: ['student'] }] };
      if (options.method === 'POST') {
        const data = JSON.parse(options.body);
        if (url.endsWith('/courses')) records.courses.push({ id: 'new-course', ...data });
        if (url.endsWith('/modules')) records.modules.push({ id: 'new-module', ...data });
        if (url.endsWith('/assignments')) records.assignments.push({ id: 'assignment', ...data });
        return {};
      }
      if (options.method === 'DELETE') records.assignments = [];
      return records;
    },
  });
  vm.runInContext(fs.readFileSync('frontend_shared/static/academic_admin.js', 'utf8'), context);
  return { node, calls, redirects, fail: error => { failure = error; } };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const event = { preventDefault() {} };

test('Admin creates courses and modules with CSRF and sees the updated catalogue', async () => {
  const { node, calls } = screen();
  await tick();
  assert.equal(node('academic-catalog-list').children[0].children[0].textContent, 'Computing <script> (COMP)');
  const course = node('create-course-form');
  course.elements.name.value = 'Engineering';
  course.elements.code.value = 'ENG';
  await course.events.submit(event);
  const module = node('create-module-form');
  module.elements.name.value = 'Materials';
  module.elements.code.value = 'MAT';
  module.elements.course_id.value = 'new-course';
  module.elements.year.value = '3';
  await module.events.submit(event);
  const writes = calls.filter(call => call.options.method === 'POST');
  assert.equal(writes.length, 2);
  assert.equal(writes[1].options.headers['X-CSRFToken'], 'token');
  assert.equal(writes[1].url, '/api/colleges/college/college/academic/modules');
  assert.deepEqual(JSON.parse(writes[1].options.body), { name: 'Materials', code: 'MAT', course_id: 'new-course', year: 3 });
  assert.equal(node('academic-catalog-list').children.length, 2);
});

test('Course assignments capture a year, module tutor assignments do not, and can be removed', async () => {
  const { node, calls } = screen();
  await tick();
  const form = node('assign-academic-user-form');
  form.elements.target.value = 'course:course';
  form.elements.target.events.change();
  assert.equal(form.elements.role.options[1].disabled, true);
  assert.equal(form.elements.year.required, true);
  form.elements.year.value = '2';
  form.elements.user_id.value = 'user';
  await form.events.submit(event);
  let writes = calls.filter(call => call.options.method === 'POST');
  assert.equal(JSON.parse(writes[0].options.body).year, 2);
  form.elements.target.value = 'module:module';
  form.elements.target.events.change();
  assert.equal(form.elements.year.disabled, true);
  assert.equal(form.elements.role.options[1].disabled, false);
  form.elements.role.value = 'tutor';
  form.elements.user_id.value = 'user';
  await form.events.submit(event);
  writes = calls.filter(call => call.options.method === 'POST');
  assert.deepEqual(JSON.parse(writes[1].options.body), { user_id: 'user', target_type: 'module', target_id: 'module', role: 'tutor' });
  await node('academic-assignment-list').children[0].children[1].events.click();
  assert(calls.some(call => call.options.method === 'DELETE' && call.options.headers['X-CSRFToken'] === 'token'));
  assert.match(node('academic-assignment-list').children[0].textContent, /No user assignments/);
});

test('Failed writes preserve entered values and expired sessions return to login', async () => {
  const { node, fail, redirects } = screen();
  await tick();
  const form = node('create-course-form');
  form.elements.name.value = 'Retry this course';
  fail(Object.assign(new Error('Session expired'), { status: 401 }));
  await form.events.submit(event);
  assert.equal(form.elements.name.value, 'Retry this course');
  assert.equal(form.submit.disabled, false);
  assert.equal(node('course-save-status').textContent, 'Session expired');
  assert.deepEqual(redirects, ['/login']);
});
