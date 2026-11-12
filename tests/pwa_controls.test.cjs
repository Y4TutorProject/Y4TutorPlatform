const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
function ui({ installed = false, online = true, userAgent = 'iPhone' } = {}) {
  const events = {}, workerEvents = {}, elements = {};
  for (const id of ['connection-status', 'pwa-install', 'pwa-install-help', 'pwa-update', 'pwa-update-notice']) {
    elements[id] = { hidden: true, addEventListener(name, cb) { this[name] = cb; } };
  }
  let reloads = 0, activations = 0;
  const registration = {
    waiting: { postMessage(message) { assert.equal(message.type, 'ACTIVATE_UPDATE'); activations++; } },
    addEventListener() {}
  };
  const navigator = { onLine: online, userAgent,
    serviceWorker: { controller: {}, register: async () => registration,
      addEventListener(name, cb) { workerEvents[name] = cb; } } };
  vm.runInNewContext(fs.readFileSync('frontend_shared/static/pwa/pwa.js', 'utf8'), {
    document: { getElementById: id => elements[id], querySelector: () => null, querySelectorAll: () => [] },
    window: { isSecureContext: true, matchMedia: () => ({ matches: installed, addEventListener() {} }),
      addEventListener(name, cb) { events[name] = cb; }, location: { reload() { reloads++; } } }, navigator, console
  });
  return { elements, events, workerEvents, navigator, reloads: () => reloads, activations: () => activations };
}

test('updates reload only after explicit acceptance in this tab', async () => {
  const app = ui();
  await Promise.resolve();
  assert.equal(app.elements['pwa-update'].hidden, false);
  app.workerEvents.controllerchange();
  assert.equal(app.reloads(), 0);
  app.elements['pwa-update'].click();
  assert.equal(app.activations(), 1);
  app.workerEvents.controllerchange();
  assert.equal(app.reloads(), 1);
});

test('installed apps hide installation guidance and offline status follows connectivity', () => {
  const app = ui({ installed: true, online: false });
  assert.equal(app.elements['pwa-install'].hidden, true);
  assert.equal(app.elements['connection-status'].hidden, false);
  app.navigator.onLine = true;
  app.events.online();
  assert.equal(app.elements['connection-status'].hidden, true);
});

test('manual installation guidance and browser prompts are available', async () => {
  const app = ui();
  assert.equal(app.elements['pwa-install'].hidden, false);
  await app.elements['pwa-install'].click();
  assert.equal(app.elements['pwa-install-help'].hidden, false);
  let prompted = false;
  app.events.beforeinstallprompt({ preventDefault() {}, async prompt() { prompted = true; }, userChoice: Promise.resolve({ outcome: 'accepted' }) });
  await app.elements['pwa-install'].click();
  assert.equal(prompted, true);
  app.events.appinstalled();
  assert.equal(app.elements['pwa-install'].hidden, true);
  assert.equal(app.elements['pwa-install-help'].hidden, true);
});

test('desktop Chrome does not show an install control when installation is available', () => {
  const app = ui({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130.0.0.0 Safari/537.36' });
  assert.equal(app.elements['pwa-install'].hidden, true);
  app.events.beforeinstallprompt({ preventDefault() {}, prompt() {}, userChoice: Promise.resolve({ outcome: 'dismissed' }) });
  assert.equal(app.elements['pwa-install'].hidden, true);
  assert.equal(app.elements['pwa-install-help'].hidden, true);
});
