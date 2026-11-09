const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

function screen({ page = 'choose-username', username = 'My_Name', failure = false,
                  user = { roles: ['student'], username_completed: true, preferences_completed: false } } = {}) {
  const calls = [], redirects = [];
  const status = { focus() {} };
  const button = { disabled: false };
  const form = {
    dataset: {}, events: {},
    elements: { username: { value: username }, email: { value: 'user@example.test' }, password: { value: 'password123' } },
    querySelector() { return button; }, reportValidity() { return true; },
    reset() {}, setAttribute() {}, removeAttribute() {},
    addEventListener(event, callback) { this.events[event] = callback; },
  };
  const ids = { 'choose-username': 'username-form', signup: 'signup-form', login: 'login-form' };
  const context = vm.createContext({
    URLSearchParams,
    document: { body: { dataset: { page } }, getElementById: id => id === 'form-status' ? status : id === ids[page] ? form : null },
    window: { location: { search: "", assign: url => redirects.push(url), replace: url => redirects.push(url) } },
    sessionStorage: { setItem() {} },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const csrf = url.endsWith('/auth/csrf');
      return { ok: csrf || !failure, status: failure ? 409 : 200,
        json: async () => csrf ? { csrf_token: 'token' } : failure ? { error: 'Username already taken' } : { user } };
    },
  });
  vm.runInContext(fs.readFileSync('frontend_shared/static/auth.js', 'utf8'), context);
  return { calls, redirects, status, button, submit: () => form.events.submit({ preventDefault() {} }) };
}

test('Username setup saves using session CSRF and continues onboarding', async () => {
  const ui = screen();
  await ui.submit();
  assert.equal(ui.calls[1].url, '/api/users/users/me/username');
  assert.equal(ui.calls[1].options.headers['X-CSRFToken'], 'token');
  assert.deepEqual(JSON.parse(ui.calls[1].options.body), { username: 'My_Name' });
  assert.deepEqual(ui.redirects, ['/preferences']);
});

test('Username conflict remains on form and allows retry', async () => {
  const ui = screen({ failure: true });
  await ui.submit();
  assert.equal(ui.status.textContent, 'Username already taken');
  assert.equal(ui.button.disabled, false);
  assert.deepEqual(ui.redirects, []);
});

test('First login asks for username before preferences', async () => {
  const ui = screen({ page: 'login', user: { username_completed: false, preferences_completed: false } });
  await ui.submit();
  assert.deepEqual(ui.redirects, ['/choose-username']);
});

for (const username of ['Chosen_Name', '']) {
  test(`Signup ${username ? 'submits a chosen username' : 'can defer username to first login'}`, async () => {
    const ui = screen({ page: 'signup', username });
    await ui.submit();
    const data = JSON.parse(ui.calls[1].options.body);
    assert.equal(data.username, username || undefined);
    assert.deepEqual(ui.redirects, ['/check-email']);
  });
}
