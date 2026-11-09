const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const definitions = [
  { id: 'moodle', label: 'Moodle', fields: [
    { name: 'programme_category_depth', label: 'Programme depth', type: 'integer', default: 2, min: 1, max: 20 },
    { name: 'year_labels', label: 'Year labels', type: 'json', default: { Y1: 1 } },
    { name: 'student_roles', label: 'Student roles', type: 'list', default: ['student'] },
    { name: 'module_source', label: 'Module source', type: 'select', default: 'courses', choices: { courses: 'Courses', activities: 'Activities' } },
  ] },
  { id: 'blackboard', label: 'Installed alternative LMS', fields: [
    { name: 'term_field', label: 'Term field', type: 'text', default: 'term' },
  ] },
];
class Element {
  constructor(tag = '') { this.tag = tag; this.children = []; this.value = ''; this.events = {}; this.dataset = {}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(name, callback) { this.events[name] = callback; }
  reportValidity() { return true; }
}
function screen(connection = null, page = '') {
  const redirects = [], calls = [], nodes = new Map();
  function node(id) { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); }
  const form = node('lms-form');
  form.elements = { provider: node('lms-provider'), api_key: node('lms-key'), base_url: node('lms-url'), enabled: node('lms-enabled') };
  form.querySelector = () => node('save-button');
  node('lms-settings').dataset = { collegeId: 'college-id' };
  const context = vm.createContext({
    document: { body: { dataset: { page } }, getElementById: node, createElement: tag => new Element(tag) },
    window: { location: { replace: url => redirects.push(url) } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => url.endsWith('/auth/csrf') ? { csrf_token: 'token' } :
        url.endsWith('/providers') ? { providers: definitions } : { connection } };
    },
  });
  vm.runInContext(fs.readFileSync('frontend_shared/static/auth.js', 'utf8'), context);
  return { node, context, redirects, calls };
}
const saved = { provider: 'moodle', base_url: 'https://college.edu', enabled: true,
  next_sync_at: '2026-11-03T02:00:00Z', timezone: 'Europe/Dublin' };

test('Provider selector and mapping fields are driven by installed adapter descriptions', async () => {
  const { node, context } = screen();
  await context.setupLMSImport('college-id');
  assert.equal(node('provider-settings').hidden, true);
  assert.deepEqual(node('lms-provider').children.map(item => item.value), ['', 'moodle', 'blackboard']);
  node('lms-provider').value = 'moodle';
  node('lms-provider').events.change();
  assert.equal(node('provider-settings').hidden, false);
  assert.equal(node('provider-mapping-options').children.length, 4);
  node('lms-key').value = 'secret';
  node('lms-provider').value = 'blackboard';
  node('lms-provider').events.change();
  assert.equal(node('lms-key').value, '');
  assert.equal(node('provider-settings').hidden, false);
  assert.equal(node('provider-mapping-options').children.length, 1);
  assert.equal(node('provider-mapping-options').children[0].children[1].value, 'term');
  node('lms-provider').value = 'unsupported';
  node('lms-provider').events.change();
  assert.equal(node('provider-settings').disabled, true);
});

test('Saved mapping settings restore and typed edits are sent with the connection', async () => {
  const { node, context, calls } = screen({ ...saved, provider_options: { programme_category_depth: 1, year_labels: { First: 1 }, student_roles: ['learner'] } });
  await context.setupLMSImport('college-id');
  const fields = node('provider-mapping-options').children.map(group => group.children[1]);
  assert.equal(fields[0].value, '1');
  assert.equal(fields[1].value, JSON.stringify({ First: 1 }, null, 2));
  fields[0].value = '3';
  fields[2].value = 'learner, student';
  await node('lms-form').events.submit({ preventDefault() {} });
  const request = calls.find(call => call.options?.method === 'PUT');
  const data = JSON.parse(request.options.body);
  assert.equal(data.provider_options.programme_category_depth, 3);
  assert.deepEqual(data.provider_options.student_roles, ['learner', 'student']);
  assert.deepEqual(data.provider_options.year_labels, { First: 1 });
  assert.equal(node('lms-key').value, '');
});

for (const stage of ['load', 'save', 'sync']) {
  test(`Expired session during ${stage} disables connection actions`, async () => {
    const { node, context, redirects } = screen(saved);
    const fail = () => { context.fetch = async url => ({ ok: url.endsWith('/auth/csrf'), status: 401,
      json: async () => url.endsWith('/auth/csrf') ? { csrf_token: 'token' } : { error: 'Authentication required.' } }); };
    if (stage === 'load') fail();
    await context.setupLMSImport('college-id');
    if (stage !== 'load') {
      fail();
      node('lms-key').value = 'private-key';
      if (stage === 'save') await node('lms-form').events.submit({ preventDefault() {} });
      else await node('lms-sync-button').events.click();
    }
    assert.deepEqual(redirects, ['/login']);
    assert.equal(node('lms-key').value, '');
    assert.equal(node('save-button').disabled, true);
    assert.equal(node('lms-sync-button').disabled, true);
    assert.match(node('lms-status').textContent, /session has expired/);
  });
}

test('Admin dashboard initializes the saved adapter and sign out', async () => {
  const { node, redirects } = screen(saved, 'dashboard');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(node('lms-url').value, 'https://college.edu');
  assert.equal(node('provider-settings').hidden, false);
  await node('logout-button').events.click();
  assert.deepEqual(redirects, ['/login']);
});
