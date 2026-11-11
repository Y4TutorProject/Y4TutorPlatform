# Desktop website and mobile PWA

TutorPlatform uses the same Flask/Jinja pages for desktop browsers, mobile browsers and the installed app. All roles remain available. It is online-first: live data and writes require a connection. Notifications, background sync and offline user-data storage are not included.

## Run and deploy

Rebuild the shared frontend consumers and gateway after changing PWA assets:

```sh
docker compose up -d --build --no-deps gateway dashboard_svc users_frontend registration_frontend messaging_svc
```

The gateway exposes `/manifest.webmanifest`, `/sw.js` and `/pwa/` through the dashboard service. The worker has `/` scope so it covers all frontend services on the same origin. Keep these public routes accessible without authentication, with correct MIME types, and do not cache `/sw.js` at a reverse proxy/CDN.

For production and phone testing, serve the gateway behind a trusted HTTPS reverse proxy on one stable domain, forwarding WebSocket upgrades for `/socket.io/`. Set `PUBLIC_BASE_URL` to that HTTPS origin and keep secure cookies enabled. Plain `http://localhost:8080` works for development on this computer; a phone accessing an ordinary LAN HTTP address does not get the same secure-context exception. No production hostname or certificate is provisioned by this change.

## Install and update

On mobile, use **Install app** where offered. Desktop pages hide the app installation control; installation remains available through the browser’s own menu. On iPhone/iPad, open the browser's Share menu and select **Add to Home Screen**, ensuring it opens as a web app. Installation controls disappear in standalone mode. Browser support and menu wording vary.

When a new worker is waiting, an update notice asks users to save their work before selecting **Update app**. Other open tabs are not automatically reloaded. Increment `CACHE` in `frontend_shared/static/pwa/sw.js` whenever a cached asset changes; its exact allowlist must include any newly cacheable public files. Never add personalised HTML, APIs, messages, uploaded files or credentials.

Only public assets are cached. Failed navigations show a generic offline screen with Retry. An installed app needs at least one successful online visit to prepare that fallback. The existing authenticated responses retain `Cache-Control: no-store`.

## Validation

```sh
PYTHONPATH=dashboard_svc .venv-auth/bin/python -m pytest tests/test_pwa.py -q
node --test tests/pwa_worker.test.cjs tests/pwa_controls.test.cjs
```

`tests/pwa_browser.cjs` provides optional Playwright smoke checks against the running gateway using an installed Chrome browser. Install Playwright in a separate tooling directory and set `NODE_PATH` to its `node_modules` directory. Set `PWA_TEST_EMAIL` and `PWA_TEST_PASSWORD` to an existing local test account to include signed-in layouts and conversation navigation; the script does not send messages. `PWA_BASE_URL` defaults to `http://localhost:8080`.

Before production release, check Home Screen installation and launch on physical Android/iPhone devices, phone keyboard behaviour, standalone safe areas, offline retry, and updating while a form contains unsaved changes. Desktop emulation does not establish physical-device compatibility.
