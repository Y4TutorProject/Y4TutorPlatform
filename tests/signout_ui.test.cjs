const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

for (const page of ['dashboard', 'student-dashboard', 'chat']) {
test(`${page} sign out waits for the API before navigating`, async () => {
  const listeners = [], calls = [], redirects = [];
  const button = { addEventListener: (name, handler) => listeners.push(handler) };
  let finishLogout;
  const context = vm.createContext({
    document: {
      body: { dataset: { page } },
      getElementById: id => id === 'logout-button' ? button : null,
      addEventListener() {},
    },
    window: { location: {
      replace: url => redirects.push(url),
      set href(url) { redirects.push(url); },
    } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (url.endsWith('/auth/logout')) {
        await new Promise(resolve => { finishLogout = resolve; });
      }
      return { ok: true, json: async () => ({ csrf_token: 'token' }) };
    },
  });
  for (const file of ['auth.js', 'dashboard.js']) {
    vm.runInContext(fs.readFileSync(`frontend_shared/static/${file}`, 'utf8'), context);
  }
  const pending = listeners.map(handler => handler());
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(redirects, []);
  assert.equal(button.disabled, true);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].url, '/api/users/auth/logout');
  assert.equal(calls[1].options.method, 'POST');
  assert.equal(calls[1].options.headers['X-CSRFToken'], 'token');
  finishLogout();
  await Promise.all(pending);
  assert.deepEqual(redirects, ['/login']);
});
}
