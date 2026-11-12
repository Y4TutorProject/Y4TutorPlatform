const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');

function worker() {
  const handlers = {};
  const stored = [];
  const cache = { match: async () => undefined, put: async (request) => stored.push(request.url) };
  let fail = false;
  const self = { location: { origin: 'https://tutor.test' }, addEventListener: (name, cb) => handlers[name] = cb };
  vm.runInNewContext(fs.readFileSync('frontend_shared/static/pwa/sw.js', 'utf8'), {
    self, URL, Set,
    caches: { open: async () => cache, match: async path => ({ offline: path }) },
    fetch: async () => {
      if (fail) throw new Error('Offline');
      return { ok: true, redirected: false, type: 'basic', clone() { return this; } };
    }
  });
  async function request(path, options = {}) {
    let response;
    handlers.fetch({ request: { url: `https://tutor.test${path}`, method: 'GET', mode: 'cors', ...options }, respondWith: promise => response = promise });
    return response;
  }
  return { request, stored, offline() { fail = true; } };
}

test('worker caches only explicitly public assets', async () => {
  const w = worker();
  await w.request('/pwa/mobile.css');
  assert.deepEqual(w.stored, ['https://tutor.test/pwa/mobile.css']);
  for (const path of ['/api/users/users/me', '/messages', '/account', '/dashboard', '/dashboard/static/unknown', '/pwa/mobile.css?user=1', '/socket.io/']) {
    assert.equal(await w.request(path), undefined);
  }
  assert.equal(await w.request('/pwa/mobile.css', { method: 'POST' }), undefined);
  assert.equal(await w.request('/pwa/mobile.css', { url: 'https://other.test/pwa/mobile.css' }), undefined);
  assert.equal(w.stored.length, 1);
});

test('navigation stays network-only and uses generic offline fallback', async () => {
  const w = worker();
  await w.request('/account', { mode: 'navigate' });
  assert.deepEqual(w.stored, []);
  w.offline();
  assert.equal((await w.request('/account', { mode: 'navigate' })).offline, '/pwa/offline.html');
  assert.deepEqual(w.stored, []);
});
