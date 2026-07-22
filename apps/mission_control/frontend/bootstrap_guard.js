(() => {
  const errorState = { rendered: false };

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function renderFailure(reason) {
    if (errorState.rendered || window.__NETLAB_APP_READY__) return;
    errorState.rendered = true;
    const root = document.getElementById('view-root');
    const nav = document.getElementById('primary-nav');
    const message = reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason || 'Unknown frontend initialization failure');
    if (nav && !nav.children.length) {
      nav.innerHTML = '<div class="nav-section">RECOVERY</div><button class="nav-item active" type="button"><span class="nav-icon">!</span><span>Frontend diagnostics</span></button>';
    }
    if (root) {
      root.innerHTML = `<section class="card"><div class="callout error"><div class="callout-title">Mission Control could not initialize</div><div>${escapeHtml(message)}</div><div class="small-text" style="margin-top:8px">Reload after checking /api/health and /modules/app.js. The control plane remains protected; no command was executed.</div></div><div class="row" style="margin-top:14px"><button id="frontend-reload" class="button primary" type="button">Reload Mission Control</button></div></section>`;
      document.getElementById('frontend-reload')?.addEventListener('click', () => location.reload());
    }
    const consoleElement = document.getElementById('event-console');
    if (consoleElement) consoleElement.textContent = message + '\n' + (reason?.stack || '');
  }

  window.__NETLAB_FRONTEND_FAILURE__ = renderFailure;
  window.addEventListener('error', event => renderFailure(event.error || event.message));
  window.addEventListener('unhandledrejection', event => renderFailure(event.reason));
  window.setTimeout(() => {
    if (!window.__NETLAB_APP_READY__) renderFailure('Frontend module startup did not complete within 8 seconds.');
  }, 8000);
})();
