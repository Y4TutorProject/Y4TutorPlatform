const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.events = {}; this.value = ''; this.dataset = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, callback) { this.events[name] = callback; }
  set innerHTML(value) { throw new Error('Imported data must be rendered as text'); }
}

function screen(failure = null) {
  const nodes = new Map(), calls = [], redirects = [], events = {};
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  const catalog = {
    provider: 'moodle', base_url: 'https://college.test', imported_at: '2026-11-10T01:00:00Z',
    courses: Array.from({ length: 27 }, (_, i) => ({ id: `course-${i}`, source_id: String(i), name: `Course ${i}`, code: `C${i}`, kind: 'programme' })),
    modules: [{ id: 'module', source_id: '42', name: '<script>alert(1)</script>', code: 'DB', course_id: 'course-0', programme_id: 'course-0', year: 2 }],
    users: [{ source_id: '10', first_name: 'A', last_name: 'Student', username: 'student', email: 'student@college.test', suspended: true, current_year: 3 }],
    enrolments: [{ user_source_id: '10', target_type: 'module', target_id: 'module', roles: ['student', 'lecturer'] }],
    enrolments_available: true,
  };
  node('lms-imported-data').dataset.collegeId = 'college';
  const type = node('lms-catalog-type');
  type.value = 'courses';
  type.options = ['courses', 'modules', 'users', 'enrolments'].map(text => ({ textContent: text }));
  Object.defineProperty(type, 'selectedIndex', { get: () => ['courses', 'modules', 'users', 'enrolments'].indexOf(type.value) });
  const context = vm.createContext({
    document: { getElementById: node, createElement: () => new Element(),
      addEventListener: (name, handler) => { events[name] = handler; } },
    window: { location: { replace: url => redirects.push(url) } },
    errorMessage: error => error.message,
    requestJSON: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/csrf')) return { csrf_token: 'token' };
      if (failure) throw failure;
      return { catalog };
    },
  });
  vm.runInContext(fs.readFileSync('frontend_shared/static/lms_catalog.js', 'utf8'), context);
  return { node, calls, redirects, catalog, events, fail: error => { failure = error; } };
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const values = row => row.children.map(cell => cell.textContent);

test('Owner catalogue requests carry CSRF and courses are paginated and searchable', async () => {
  const { node, calls } = screen();
  await tick();
  assert.equal(calls[1].url, '/api/lms/college/college/lms/catalog');
  assert.equal(calls[1].options.headers['X-CSRFToken'], 'token');
  assert.equal(node('lms-catalog-browser').hidden, false);
  assert.match(node('lms-catalog-status').textContent, /27 course/);
  assert.equal(node('lms-catalog-rows').children.length, 25);
  node('lms-catalog-next').events.click();
  assert.equal(node('lms-catalog-rows').children.length, 2);
  assert.match(node('lms-catalog-page').textContent, /Page 2 of 2/);
  node('lms-catalog-search').value = 'C26';
  node('lms-catalog-search').events.input();
  assert.equal(node('lms-catalog-rows').children.length, 1);
  assert.equal(values(node('lms-catalog-rows').children[0])[0], 'Course 26');
  assert.match(node('lms-catalog-page').textContent, /Page 1 of 1/);
});

test('Modules, users and enrolments show resolved relationships and safe text', async () => {
  const { node } = screen();
  await tick();
  for (const [category, expected] of [
    ['modules', ['<script>alert(1)</script>', 'DB', 'Course 0 (C0)', 'Course 0 (C0)', '2', '42']],
    ['users', ['A Student', 'student', 'student@college.test', '3', 'Suspended', '10']],
    ['enrolments', ['A Student', 'student@college.test', '<script>alert(1)</script> (DB)', 'student, lecturer']],
  ]) {
    node('lms-catalog-type').value = category;
    node('lms-catalog-type').events.change();
    assert.deepEqual(values(node('lms-catalog-rows').children[0]), expected);
  }
  node('lms-catalog-search').value = 'nothing matches';
  node('lms-catalog-search').events.input();
  assert.match(node('lms-catalog-rows').children[0].children[0].textContent, /No imported records match/);
});

test('A successful sync refreshes the snapshot and empty enrolments are explained', async () => {
  const { node, catalog, events } = screen();
  await tick();
  catalog.users = [];
  catalog.enrolments = [];
  catalog.enrolments_available = false;
  await events['lms-catalog-updated']();
  assert.match(node('lms-catalog-status').textContent, /0 user/);
  assert.match(node('lms-catalog-status').textContent, /Enrolment data was not available/);
});

test('Missing imports, denied access and expired sessions hide the catalogue', async () => {
  for (const status of [404, 403, 401]) {
    const { node, redirects } = screen(Object.assign(new Error('Access denied'), { status }));
    await tick();
    assert.equal(node('lms-catalog-browser').hidden, true);
    assert.equal(node('refresh-lms-data').disabled, false);
    assert.match(node('lms-catalog-status').textContent, status === 404 ? /No imported data yet/ : /Access denied/);
    assert.deepEqual(redirects, status === 401 ? ['/login'] : []);
  }
});
