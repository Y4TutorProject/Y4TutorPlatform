/* Optional browser smoke check: NODE_PATH=<playwright node_modules> node tests/pwa_browser.cjs
 * PWA_BASE_URL defaults to localhost:8080. Set PWA_TEST_EMAIL/PWA_TEST_PASSWORD
 * to additionally check authenticated dashboard, account and messaging layouts.
 */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = process.env.PWA_BASE_URL || 'http://localhost:8080';
    const noOverflow = async label => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${label}: horizontal overflow`);
    const widths = [360, 390, 768, 1440];
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of ['/login', '/signup', '/signup/student', '/signup/college-admin']) {
        await page.goto(base + path);
        await noOverflow(`${path} at ${width}px`);
      }
    }
    console.log('Public responsive layouts passed; checking service worker.');
    await page.waitForFunction(async () => !!(await navigator.serviceWorker.getRegistration())?.active);
    await page.waitForFunction(() => !!navigator.serviceWorker.controller);
    const manifest = await (await page.request.get(base + '/manifest.webmanifest')).json();
    assert.equal(manifest.display, 'standalone');
    assert.equal(manifest.start_url, '/dashboard');
    console.log('Service worker active; checking offline navigation.');
    await context.setOffline(true);
    await page.goto(base + '/account');
    assert.equal(await page.locator('h1').innerText(), 'You’re offline');
    await context.setOffline(false);
    await page.locator('a').click();
    await page.waitForURL('**/login');
    if (process.env.PWA_TEST_EMAIL && process.env.PWA_TEST_PASSWORD) {
      console.log('Offline retry passed; checking authenticated layouts.');
      const loginStatus = await page.evaluate(async credentials => {
        const csrf = await (await fetch('/api/users/auth/csrf')).json();
        return (await fetch('/api/users/auth/login', {
          method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf.csrf_token },
          body: JSON.stringify(credentials)
        })).status;
      }, { email: process.env.PWA_TEST_EMAIL, password: process.env.PWA_TEST_PASSWORD });
      assert.equal(loginStatus, 200, 'Test account login');
      for (const width of widths) {
        await page.setViewportSize({ width, height: 900 });
        for (const path of ['/dashboard', '/account', '/preferences', '/messages']) {
          await page.goto(base + path);
          assert(!page.url().endsWith('/login'), `${path}: authenticated navigation`);
          await noOverflow(`${path} at ${width}px`);
          if (width < 768 && await page.locator('.platform-menu-toggle').count()) {
            await page.locator('.platform-menu-toggle').click();
            assert(await page.locator('.platform-nav-actions').isVisible());
            await page.keyboard.press('Escape');
            assert.equal(await page.locator('.platform-nav-actions').isVisible(), false);
          }
        }
      }
      await page.setViewportSize({ width: 390, height: 844 });
      const firstChat = page.locator('.chat-item').first();
      if (await firstChat.count()) {
        const chatId = await firstChat.getAttribute('data-chat-id');
        const cacheControl = await page.evaluate(async id => {
          const response = await fetch('/api/messaging/mychats/chat/' + encodeURIComponent(id));
          return response.headers.get('Cache-Control');
        }, chatId);
        assert.equal(cacheControl, 'no-store', 'Private messages must not be HTTP cached');
        await firstChat.click();
        assert(await page.locator('.messages-conversation').isVisible());
        assert.equal(await page.locator('.messages-sidebar').isVisible(), false);
        await page.locator('#message-input').fill('Unsent mobile draft');
        await page.locator('#chat-back').click();
        assert(await page.locator('.messages-sidebar').isVisible());
        await firstChat.click();
        assert.equal(await page.locator('#message-input').inputValue(), 'Unsent mobile draft');
        await context.setOffline(true);
        await page.waitForFunction(() => document.getElementById('send-btn').disabled);
        assert.equal(await page.locator('#message-input').inputValue(), 'Unsent mobile draft');
        await context.setOffline(false);
        await page.waitForFunction(() => !document.getElementById('send-btn').disabled);
        await page.screenshot({ path: '/tmp/tutorplatform-mobile-messages.png' });
        await page.setViewportSize({ width: 390, height: 430 });
        await page.locator('#message-input').focus();
        await page.waitForFunction(() => document.getElementById('message-box').getBoundingClientRect().bottom <= innerHeight + 1,
          null, { timeout: 5000 });
      }
    }
    const cachedPaths = await page.evaluate(async () => {
      const paths = [];
      for (const key of await caches.keys()) {
        if (!key.startsWith('tutorplatform-public-')) continue;
        for (const req of await (await caches.open(key)).keys()) paths.push(new URL(req.url).pathname);
      }
      return paths;
    });
    assert(cachedPaths.includes('/pwa/offline.html'));
    assert(cachedPaths.every(path => path.startsWith('/pwa/') || /\/(dashboard|users|registration)\/static\//.test(path)));
    assert.deepEqual(errors, []);
    console.log(`PWA browser checks passed: responsive layouts, manifest, worker, offline retry, public-only cache${process.env.PWA_TEST_EMAIL ? ', authenticated navigation and messaging' : ''}.`);
    await context.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
