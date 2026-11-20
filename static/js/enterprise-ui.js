/* Progressive presentation enhancements for the public site.
   Nothing here submits data or changes application behaviour. */
(() => {
  'use strict';

  const onReady = (callback) =>
    document.readyState === 'loading'
      ? document.addEventListener('DOMContentLoaded', callback, { once: true })
      : callback();

  onReady(() => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    const navbar = document.querySelector('.site-navbar');
    if (navbar) {
      const updateHeader = () => {
        const stuck = window.scrollY > 96;
        navbar.classList.toggle('is-stuck', stuck);
        if (stuck) {
          navbar.setAttribute('data-stuck', 'true');
        } else {
          navbar.removeAttribute('data-stuck');
        }
      };
      updateHeader();
      window.addEventListener('scroll', updateHeader, { passive: true });
      window.addEventListener('resize', updateHeader, { passive: true });
    }

    const finder = document.querySelector('[data-site-finder]');
    if (!finder) return;

    const toggle = finder.querySelector('[data-finder-toggle]');
    const panel = finder.querySelector('[data-finder-panel]');
    const input = finder.querySelector('[data-finder-input]');
    const results = finder.querySelector('[data-finder-results]');
    const empty = finder.querySelector('[data-finder-empty]');
    const dataNode = document.getElementById('site-finder-data');

    if (!toggle || !panel || !input || !results || !empty || !dataNode) return;

    let entries = [];
    try {
      const parsed = JSON.parse(dataNode.textContent);
      if (Array.isArray(parsed)) entries = parsed;
    } catch (error) {
      entries = [];
    }

    const setOpen = (open) => {
      panel.hidden = !open;
      toggle.setAttribute('aria-expanded', String(open));
      if (open) {
        input.value = '';
        render('');
        input.focus();
      }
    };

    const render = (query) => {
      const term = query.trim().toLowerCase();
      const matches = entries
        .filter((entry) => {
          if (!term) return true;
          return `${entry.title} ${entry.description} ${entry.group}`
            .toLowerCase()
            .includes(term);
        })
        .slice(0, 8);

      while (results.firstChild) results.removeChild(results.firstChild);
      empty.hidden = matches.length > 0;

      matches.forEach((entry) => {
        const item = document.createElement('li');
        const link = document.createElement('a');
        const title = document.createElement('span');
        const description = document.createElement('small');

        link.href = entry.url;
        title.textContent = entry.title;
        description.textContent = entry.description;
        link.append(title, description);
        item.appendChild(link);
        results.appendChild(item);
      });
    };

    toggle.addEventListener('click', (event) => {
      event.stopPropagation();
      setOpen(panel.hidden);
    });

    input.addEventListener('input', () => render(input.value));

    document.addEventListener('click', (event) => {
      if (!finder.contains(event.target)) setOpen(false);
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !panel.hidden) {
        setOpen(false);
        toggle.focus();
      }
    });

    render('');

    if (reducedMotion.matches) {
      document.documentElement.setAttribute('data-reduced-motion', 'true');
    }
  });
})();
