(() => {
  const byId = id => document.getElementById(id);
  const connection = byId('connection-status');
  const install = byId('pwa-install');
  const help = byId('pwa-install-help');
  const update = byId('pwa-update');
  const notice = byId('pwa-update-notice');
  const standalone = window.matchMedia('(display-mode: standalone)');
  let installPrompt = null;
  let registration;
  let acceptedUpdate = false;
  const isInstalled = () => standalone.matches || navigator.standalone === true;
  function connectionChanged() { connection.hidden = navigator.onLine; }
  connectionChanged();
  window.addEventListener('online', connectionChanged);
  window.addEventListener('offline', connectionChanged);
  function installationChanged() {
    const manual = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    // Keep app installation controls on mobile; desktop users can use the browser menu.
    install.hidden = isInstalled() || !manual;
    if (isInstalled() || !manual) help.hidden = true;
  }
  installationChanged();
  standalone.addEventListener('change', installationChanged);
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    installationChanged();
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    install.hidden = help.hidden = true;
  });
  install.addEventListener('click', async () => {
    if (!installPrompt) { help.hidden = !help.hidden; return; }
    const prompt = installPrompt;
    installPrompt = null;
    await prompt.prompt();
    await prompt.userChoice;
    installationChanged();
  });
  const menu = document.querySelector('.platform-menu-toggle');
  if (menu) {
    document.querySelector('.platform-nav').classList.add('menu-ready');
    menu.addEventListener('click', () => {
      const open = menu.getAttribute('aria-expanded') !== 'true';
      menu.setAttribute('aria-expanded', String(open));
      document.querySelector('.platform-nav-actions').classList.toggle('is-open', open);
    });
    menu.closest('nav').addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        menu.setAttribute('aria-expanded', 'false');
        document.querySelector('.platform-nav-actions').classList.remove('is-open');
        menu.focus();
      }
    });
  }
  // Wrap existing and dynamically rendered admin tables without clipping forms.
  function wrapTables() {
    document.querySelectorAll('main table').forEach(table => {
      if (table.parentElement.classList.contains('table-responsive')) return;
      const wrapper = document.createElement('div');
      wrapper.className = 'table-responsive';
      wrapper.tabIndex = 0;
      wrapper.setAttribute('role', 'region');
      wrapper.setAttribute('aria-label', table.getAttribute('aria-label') || 'Scrollable table');
      table.before(wrapper);
      wrapper.append(table);
    });
  }
  wrapTables();
  const main = document.querySelector('main');
  if (main) new MutationObserver(wrapTables).observe(main, { childList: true, subtree: true });
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (acceptedUpdate) window.location.reload();
  });
  update.addEventListener('click', () => {
    if (!registration?.waiting) return;
    acceptedUpdate = true;
    registration.waiting.postMessage({ type: 'ACTIVATE_UPDATE' });
  });
  function showUpdate() {
    if (registration.waiting && navigator.serviceWorker.controller) update.hidden = notice.hidden = false;
  }
  navigator.serviceWorker.register('/sw.js', { scope: '/', updateViaCache: 'none' }).then(result => {
    registration = result;
    showUpdate();
    result.addEventListener('updatefound', () => {
      const worker = result.installing;
      worker?.addEventListener('statechange', showUpdate);
    });
  }).catch(error => console.warn('App installation support unavailable:', error));
})();
