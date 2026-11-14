/* Progressive enhancements: Django remains the source of truth for every action. */
(() => {
  'use strict';
  const onReady = (callback) => document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', callback) : callback();
  onReady(() => {
    const region = document.querySelector('[data-toast-region]');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const toastTimers = new WeakMap();
    let fabObserver = null;
    function dismissToast(toast) {
      clearTimeout(toastTimers.get(toast));
      if (reducedMotion.matches) { toast.remove(); return; }
      toast.classList.add('is-leaving');
      toast.addEventListener('animationend', () => toast.remove(), { once: true });
      setTimeout(() => toast.remove(), 250);
    }
    function prepareToast(toast) {
      if (toast.dataset.prepared) return;
      toast.dataset.prepared = 'true';
      const tone = toast.dataset.tone;
      if (tone === 'error' || tone === 'warning') return;
      const start = () => toastTimers.set(toast, setTimeout(() => dismissToast(toast), 10000));
      const stop = () => clearTimeout(toastTimers.get(toast));
      toast.addEventListener('mouseenter', stop);
      toast.addEventListener('mouseleave', start);
      toast.addEventListener('focusin', stop);
      toast.addEventListener('focusout', start);
      start();
    }
    function notify(message, tone = 'info') {
      if (!region) return;
      const toast = document.createElement('div');
      toast.className = 'ui-toast';
      toast.dataset.toast = '';
      toast.dataset.tone = ['success', 'error', 'warning', 'info'].includes(tone) ? tone : 'info';
      toast.setAttribute('role', tone === 'error' ? 'alert' : 'status');
      const mark = document.createElement('span');
      mark.className = 'ui-toast-mark'; mark.setAttribute('aria-hidden', 'true');
      const content = document.createElement('p'); content.textContent = String(message);
      const close = document.createElement('button'); close.type = 'button'; close.className = 'ui-icon-control';
      close.dataset.toastDismiss = ''; close.setAttribute('aria-label', 'Dismiss notification'); close.textContent = '\u00d7';
      toast.append(mark, content, close); region.append(toast); prepareToast(toast);
      return toast;
    }
    document.querySelectorAll('[data-toast]').forEach(prepareToast);
    document.addEventListener('nasil:notify', (event) => { if (event.detail?.message) notify(event.detail.message, event.detail.tone); });
    document.addEventListener('click', (event) => {
      const close = event.target.closest('[data-toast-dismiss]');
      if (close) dismissToast(close.closest('[data-toast]'));
    });

    // Keep native table headers and add visible mobile labels without duplicating records.
    function enhanceContent(root = document) {
      fabObserver?.disconnect();
      const fab = root.querySelector('[data-fab]');
      if (fab && window.IntersectionObserver) {
        const primary = [...root.querySelectorAll('.workflow-header a')].find(link => link.href === fab.href);
        if (primary) {
          fabObserver = new IntersectionObserver(entries => { fab.hidden = entries[0].isIntersecting; }, {threshold:0});
          fabObserver.observe(primary);
        }
      }
      root.querySelectorAll('[data-range-select]').forEach(select => {
        if (select.dataset.sliderReady) return;
        select.dataset.sliderReady = 'true';
        const options = [...select.options];
        const wrap = document.createElement('div'); wrap.className = 'ui-period-control';
        const label = document.createElement('label'); label.htmlFor = 'ui-chart-period'; label.textContent = 'Booking period';
        const output = document.createElement('output'); output.id = 'ui-chart-period-value';
        const slider = document.createElement('input'); slider.type = 'range'; slider.min = '0'; slider.max = String(options.length - 1); slider.step = '1'; slider.id = 'ui-chart-period';
        slider.value = String(Math.max(0, select.selectedIndex)); slider.setAttribute('aria-describedby', output.id);
        const update = () => { const option = options[Number(slider.value)]; select.value = option.value; output.textContent = option.textContent; slider.setAttribute('aria-valuetext', option.textContent); };
        slider.addEventListener('input', update); update();
        wrap.append(label, output, slider); select.before(wrap); select.hidden = true;
      });
      root.querySelectorAll('.workflow-table, .operations-table, .portal-table-wrap table, .table-responsive table').forEach((table) => {
        if (table.dataset.mobileReady) return;
        const headers = [...table.querySelectorAll('thead tr:first-child th')];
        if (!headers.length || headers.some(header => header.colSpan > 1 || header.rowSpan > 1)) return;
        table.dataset.mobileReady = 'true';
        table.classList.add('ui-responsive-table');
        table.setAttribute('role', 'table');
        table.querySelectorAll('thead, tbody').forEach(section => section.setAttribute('role', 'rowgroup'));
        table.querySelectorAll('tr').forEach(row => row.setAttribute('role', 'row'));
        headers.forEach(header => { header.setAttribute('scope', 'col'); header.setAttribute('role', 'columnheader'); });
        table.querySelectorAll('tbody tr').forEach(row => {
          [...row.cells].forEach((cell, index) => {
            cell.setAttribute('role', 'cell');
            if (cell.colSpan > 1) return;
            const label = document.createElement('span');
            label.className = 'ui-cell-label'; label.setAttribute('aria-hidden', 'true');
            label.textContent = headers[index]?.textContent.trim() || 'Actions';
            const content = document.createElement('div'); content.className = 'ui-cell-content';
            while (cell.firstChild) content.append(cell.firstChild);
            cell.append(label, content);
          });
        });
      });
      root.querySelectorAll('.workflow-field, .website-app .form-group').forEach((field, index) => {
        const controls = field.querySelectorAll('input, select, textarea');
        const help = field.querySelector('.workflow-help');
        const errors = [...field.querySelectorAll('.workflow-error, .errorlist, .text-danger[role=alert]')];
        const firstId = controls[0]?.id || `ui-field-${index}`;
        if (help && !help.id) help.id = `${firstId}-help`;
        errors.forEach((error, i) => { if (!error.id) error.id = `${firstId}-error-${i}`; });
        controls.forEach(control => {
          const descriptions = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
          if (help) descriptions.add(help.id);
          errors.forEach(error => descriptions.add(error.id));
          if (descriptions.size) control.setAttribute('aria-describedby', [...descriptions].join(' '));
          if (errors.length) control.setAttribute('aria-invalid', 'true');
        });
      });
      root.querySelectorAll('img:not([loading])').forEach(image => {
        if (image.getBoundingClientRect().top > innerHeight) { image.loading = 'lazy'; image.decoding = 'async'; }
      });
    }
    enhanceContent();
    document.querySelectorAll('.site-navigation > .site-menu > li > a').forEach(link => {
      if (new URL(link.href).pathname === location.pathname) {
        link.setAttribute('aria-current', 'page'); link.closest('li').classList.add('active');
      }
    });

    const siteMenu = document.querySelector('.site-mobile-menu');
    if (siteMenu) {
      const opener = document.querySelector('.site-navbar .js-menu-toggle');
      const updateSiteMenu = (open) => {
        document.body.classList.toggle('offcanvas-menu', open);
        siteMenu.inert = !open; siteMenu.setAttribute('aria-hidden', String(!open));
        opener?.setAttribute('aria-expanded', String(open));
        if (open) siteMenu.querySelector('button, a')?.focus(); else opener?.focus();
      };
      siteMenu.inert = true; siteMenu.setAttribute('aria-hidden', 'true');
      siteMenu.setAttribute('role', 'dialog'); siteMenu.setAttribute('aria-modal', 'true'); siteMenu.setAttribute('aria-label', 'Website navigation');
      document.addEventListener('click', event => {
        const toggle = event.target.closest('.js-menu-toggle');
        if (toggle) { event.preventDefault(); updateSiteMenu(!document.body.classList.contains('offcanvas-menu')); }
        else if (document.body.classList.contains('offcanvas-menu') && !siteMenu.contains(event.target)) updateSiteMenu(false);
      });
      document.addEventListener('keydown', event => {
        if (!document.body.classList.contains('offcanvas-menu')) return;
        if (event.key === 'Escape') { updateSiteMenu(false); return; }
        if (event.key === 'Tab') {
          const items = [...siteMenu.querySelectorAll('a, button')].filter(item => item.getClientRects().length && !item.closest('[hidden]'));
          const first = items[0], last = items.at(-1);
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
      });
      matchMedia('(min-width: 1200px)').addEventListener('change', event => { if (event.matches && document.body.classList.contains('offcanvas-menu')) updateSiteMenu(false); });
    }

    const portalNav = document.getElementById('portal-navigation');
    const portalToggle = document.querySelector('[data-portal-menu]');
    if (portalNav && portalToggle) {
      portalNav.classList.add('is-enhanced');
      portalToggle.hidden = false;
      portalToggle.setAttribute('aria-expanded', 'false');
      const close = () => { portalNav.classList.remove('is-open'); portalToggle.setAttribute('aria-expanded', 'false'); };
      portalToggle.addEventListener('click', () => {
        const open = portalNav.classList.toggle('is-open');
        portalToggle.setAttribute('aria-expanded', String(open));
      });
      document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && portalNav.classList.contains('is-open')) { close(); portalToggle.focus(); }
      });
      document.addEventListener('click', event => { if (!portalNav.contains(event.target) && !portalToggle.contains(event.target)) close(); });
    }

    const dialog = document.querySelector('[data-confirm-dialog]');
    let confirmation = null;
    if (dialog && typeof dialog.showModal === 'function') {
      document.addEventListener('submit', (event) => {
        const submitter = event.submitter;
        const message = submitter?.dataset.confirmMessage || event.target.dataset.confirmMessage;
        if (!message || event.defaultPrevented) return;
        if (event.target.dataset.confirmed === 'true') { delete event.target.dataset.confirmed; return; }
        event.preventDefault();
        confirmation = { form: event.target, submitter, previousFocus: document.activeElement };
        dialog.querySelector('#ui-confirm-description').textContent = message;
        dialog.querySelector('[data-confirm-accept]').textContent = submitter?.textContent.trim() || 'Confirm';
        dialog.returnValue = ''; dialog.showModal();
      });
      dialog.addEventListener('click', (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close('cancel');
      });
      dialog.addEventListener('close', () => {
        const pending = confirmation; confirmation = null;
        if (!pending) return;
        pending.previousFocus?.focus();
        if (dialog.returnValue === 'confirm') { pending.form.dataset.confirmed = 'true'; pending.form.requestSubmit(pending.submitter || undefined); }
      });
    }

    // Enhance only same-page GET filters/pagination. Writes remain native CSRF-protected POSTs.
    const main = document.querySelector('main[data-enhance-pages]');
    let pendingRequest = null;
    let historyKey = 0;
    async function loadPage(url, { push = true } = {}) {
      if (!main || !window.fetch || !window.AbortController) { location.assign(url); return; }
      pendingRequest?.abort();
      const controller = new AbortController(); pendingRequest = controller;
      let timedOut = false;
      const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 20000);
      const content = main.querySelector('[data-page-content]');
      const skeleton = main.querySelector('[data-page-loading]');
      const status = main.querySelector('[data-loading-status]');
      const kind = content.querySelector('.kpi-grid, .portal-kpis') ? 'cards' : content.querySelector('table') ? 'table' : 'form';
      skeleton.dataset.kind = kind; skeleton.hidden = false;
      content.hidden = true; main.setAttribute('aria-busy', 'true'); status.textContent = 'Loading updated results.';
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal, headers: { 'Accept': 'text/html' }, cache: 'no-store' });
        if (response.redirected && new URL(response.url).pathname !== location.pathname) { location.assign(response.url); return; }
        if (!response.ok || !(response.headers.get('content-type') || '').includes('text/html')) throw new Error('response');
        const incoming = new DOMParser().parseFromString(await response.text(), 'text/html');
        if (controller.signal.aborted) return;
        const next = incoming.querySelector('main[data-enhance-pages] [data-page-content]');
        if (!next) { location.assign(response.url || url); return; }
        // Content comes only from our own same-origin Django templates. No fetched scripts run.
        next.querySelectorAll('script').forEach(script => script.remove());
        content.replaceChildren(...next.childNodes);
        document.title = incoming.title;
        if (push) history.pushState({ nasilResults: ++historyKey }, '', response.url || url);
        enhanceContent(content);
        incoming.querySelectorAll('[data-toast]').forEach(toast => {
          const copy = toast.cloneNode(true); delete copy.dataset.prepared; region?.append(copy); prepareToast(copy);
        });
        if (!reducedMotion.matches) {
          content.classList.add('is-entering');
          content.addEventListener('animationend', () => content.classList.remove('is-entering'), { once: true });
        }
        status.textContent = 'Results updated.';
        main.focus({ preventScroll: true });
        main.scrollIntoView({ block: 'start', behavior: 'instant' });
        document.dispatchEvent(new CustomEvent('nasil:content-updated'));
      } catch (error) {
        if (error.name !== 'AbortError' || timedOut) { status.textContent = 'Results could not be loaded.'; notify('We could not load those results. Your current view is unchanged. Check your connection and try again.', 'error'); }
      } finally {
        clearTimeout(timeout);
        if (pendingRequest === controller) {
          pendingRequest = null; skeleton.hidden = true; content.hidden = false; main.removeAttribute('aria-busy');
        }
      }
    }
    if (main) {
      document.addEventListener('submit', event => {
        const form = event.target;
        if (event.defaultPrevented || !main.contains(form)) return;
        if ((form.method || '').toLowerCase() === 'post') {
          if (!navigator.onLine) { event.preventDefault(); notify('You are offline. Reconnect before submitting this form.', 'warning'); return; }
          // Leave names, values, files and submitters untouched for native submission.
          main.querySelector('[data-page-content]').hidden = true;
          const loading = main.querySelector('[data-page-loading]'); loading.dataset.kind = 'form'; loading.hidden = false;
          main.setAttribute('aria-busy', 'true'); main.querySelector('[data-loading-status]').textContent = 'Submitting your form.';
          return;
        }
        if ((form.method || '').toLowerCase() !== 'get' || event.submitter?.hasAttribute('formaction')) return;
        const url = new URL(form.action || location.href, location.href);
        if (url.origin !== location.origin || url.pathname !== location.pathname) return;
        url.search = '';
        new FormData(form).forEach((value, key) => { if (typeof value === 'string') url.searchParams.append(key, value); });
        if (event.submitter?.name) url.searchParams.set(event.submitter.name, event.submitter.value);
        if (url.searchParams.has('format')) return;
        event.preventDefault(); loadPage(url.href);
      });
      document.addEventListener('click', event => {
        const link = event.target.closest('.ui-pagination a, [data-filter-reset]');
        if (!link || !main.contains(link) || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
        const url = new URL(link.href);
        if (url.origin !== location.origin || url.pathname !== location.pathname || url.searchParams.has('format')) return;
        event.preventDefault(); loadPage(url.href);
      });
      // A results-only history entry never changes module; other entries use native navigation.
      history.replaceState({ ...history.state, nasilResults: historyKey }, '', location.href);
      addEventListener('popstate', event => { if (event.state?.nasilResults !== undefined) loadPage(location.href, { push: false }); else location.reload(); });
      addEventListener('pageshow', () => {
        main.querySelector('[data-page-content]').hidden = false;
        main.querySelector('[data-page-loading]').hidden = true;
        main.removeAttribute('aria-busy');
      });
    }
    let offlineToast = null;
    addEventListener('offline', () => { offlineToast ||= notify('You are offline. Reconnect and check the record before retrying a save.', 'warning'); });
    addEventListener('online', () => { if (offlineToast) dismissToast(offlineToast); offlineToast = null; notify('Connection restored.', 'success'); });
    if (!navigator.onLine) offlineToast = notify('You are offline. Reconnect before submitting changes.', 'warning');
  });
})();
