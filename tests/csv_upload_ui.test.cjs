const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.events = {}; this.dataset = {}; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  addEventListener(name, handler) { this.events[name] = handler; }
  reportValidity() { return true; }
  querySelector() { return this.submit; }
  set innerHTML(value) { throw new Error('CSV values must be rendered as text'); }
}

function screen(status = 200) {
  const nodes = new Map(), calls = [], events = [], redirects = [];
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  node('academic-csv-upload').dataset.collegeId = 'college';
  for (const kind of ['modules', 'users']) {
    node(`csv-${kind}-form`).elements = { file: new Element() };
    node(`csv-${kind}-form`).elements.file.files = [{ name: `${kind}.csv`, size: 200 }];
    node(`csv-${kind}-form`).submit = new Element();
    node(`csv-${kind}-apply`).disabled = true;
  }
  const context = vm.createContext({
    document: { getElementById: node, createElement: () => new Element(), dispatchEvent: event => events.push(event.type) },
    Event: class { constructor(type) { this.type = type; } },
    FormData: class { constructor() { this.values = new Map(); } append(key, value) { this.values.set(key, value); } get(key) { return this.values.get(key); } },
    requestJSON: async () => ({ csrf_token: 'token' }),
    errorMessage: error => error.message,
    window: { location: { replace: url => redirects.push(url) } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const applied = options.body.get('dry_run') === 'false';
      return { ok: status === 200, status, json: async () => status === 200 ? {
        valid: true, applied, rows: 1, summary: { modules_created: 1 },
        preview: [{ row: 2, module_name: '<img src=x>' }], errors: [], error_count: 0,
      } : status === 422 ? { valid: false, applied: false, error_count: 1,
        errors: [{ row: 3, message: 'Year must be 1–20.' }], preview: [] } : { error: 'Access denied' } };
    },
  });
  vm.runInContext(fs.readFileSync('frontend_shared/static/csv_upload.js', 'utf8'), context);
  return { node, calls, events, redirects };
}
const event = { preventDefault() {} };

test('CSV must be previewed before applying and multipart uploads include CSRF', async () => {
  const { node, calls, events } = screen();
  const form = node('csv-modules-form');
  await node('csv-modules-apply').events.click();
  assert.equal(calls.length, 0);
  await form.events.submit(event);
  assert.equal(calls[0].url, '/api/colleges/college/college/academic/import/modules');
  assert.equal(calls[0].options.headers['X-CSRFToken'], 'token');
  assert.equal(calls[0].options.headers['Content-Type'], undefined);
  assert.equal(calls[0].options.body.get('dry_run'), 'true');
  assert.equal(node('csv-modules-apply').disabled, false);
  assert.equal(node('csv-modules-rows').children[0].children[1].textContent, '<img src=x>');
  await node('csv-modules-apply').events.click();
  assert.equal(calls[1].options.body.get('dry_run'), 'false');
  assert.deepEqual(events, ['academic-data-updated']);
  assert.equal(node('csv-modules-apply').disabled, true);
  assert.match(node('csv-modules-status').textContent, /Import complete/);
});

test('Changing the selected file invalidates the old preview', async () => {
  const { node, calls } = screen();
  const form = node('csv-users-form');
  await form.events.submit(event);
  const file = form.elements.file;
  file.files = [{ name: 'other.csv', size: 100 }];
  file.events.change();
  assert.equal(node('csv-users-apply').disabled, true);
  await node('csv-users-apply').events.click();
  assert.equal(calls.length, 1);
});

test('Row errors disable import and display the CSV line number', async () => {
  const { node, calls } = screen(422);
  await node('csv-modules-form').events.submit(event);
  assert.equal(node('csv-modules-apply').disabled, true);
  assert.equal(node('csv-modules-errors').children[0].textContent, 'Row 3: Year must be 1–20.');
  assert.match(node('csv-modules-status').textContent, /No records were saved/);
  assert.equal(calls.length, 1);
});

test('Large files are rejected before upload and expired sessions return to login', async () => {
  const ui = screen();
  ui.node('csv-users-form').elements.file.files[0].size = 2 * 1024 * 1024;
  await ui.node('csv-users-form').events.submit(event);
  assert.equal(ui.calls.length, 0);
  assert.match(ui.node('csv-users-status').textContent, /up to 1 MB/);
  const expired = screen(401);
  await expired.node('csv-users-form').events.submit(event);
  assert.deepEqual(expired.redirects, ['/login']);
  assert.equal(expired.node('csv-users-form').elements.file.disabled, false);
});
