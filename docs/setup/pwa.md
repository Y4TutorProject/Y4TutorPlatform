# Desktop website and mobile PWA

Thanks to PWA capabilities the TutorPlatform uses the same Flask and Jinja pages on desktop and mobile, mobile allowing users to download the app to their device. Users need an online connection to load data and save changed.

## Run and deploy

After changing the PWA files, rebuild the frontends that use them and the gateway:

```sh
docker compose up -d --build --no-deps gateway dashboard_svc users_frontend registration_frontend messaging_svc
```

The dashbaord service serves `/manifest.webmanifest, /sw.js` and `/pwa/` through the gateway. The service worker's scope is `/`, so it covers all frontend pages on that origin. These routes must be public and return the correct MIME types.

For production ortesting on a phone, put the gateway behind a HTTPS reverse proxy on a stable domain. Forward WebSocket upgrades for `/socket.io/`, set `PUBLIC_BASE_URL` to the HTTPS origin and keep secure cookies enabled.

You can use `http://localhost:8080` for development on this computer. A phone opening an ordinary HTTP address on the local network does not get the browser's [localhost](http://localhost) security exception. The production domain and certificate need to be configured separately.

## Install and update

On mobile, select **Install app** when it is available.  On iPhone or iPad, use the browser's Share menu and choose **Add to Home Screen,** making sure it opens as a web app. The button is hidden when the app is already running in standalone mode.

Desktop pages do not show the install button, but users can still install through the browser's own menu. When an update is ready, users see a notice asking them to save their work before selecting **Update app.** Other open tabs are left as they are.

Change the `CACHE` version in `frontend_shared/static/pwa/sw.js` whenever a cached file changes. Add new public files to its allowed list if they should be cached. Keep personalised HTML, API responses, messages, uploads and credentails out of that list.

Only public files are cached. If a page cannot load because the connection is down, the app shows an offline page with a retry link. This needs at least one successful online visit to prepare the offline page. Authenticated responses keep `Cache-Control: no-store`

## Validation

```sh
PYTHONPATH=dashboard_svc .venv-auth/bin/python -m pytest tests/test_pwa.py -q
node --test tests/pwa_worker.test.cjs tests/pwa_controls.test.cjs
```

`tests/pwa_browser.cjs` provides optional Playwright smoke checks against the running gateway using an installed Chrome browser. Install Playwright in a seperate tooling directory and set `NODE_PATH` to its `node_modules` directory. Set `PWA_TEST_EMAIL` and `PWA_TEST_PASSWORD` to an existing local test account to include signed-in layouts and conversation navigation; the script does not send messages. `PWA_BASE_URL` defaults to `http://localhost:8080`.

Before release, test on actual Android and iPhone devices. Check installation, launching from the Home Screen,  the phone keyboard, screen edges and safe area, offline retry, and updates while a form has unsaved changes. Desktop emulation alone is not enough for these checks.
