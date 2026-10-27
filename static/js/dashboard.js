document.addEventListener("DOMContentLoaded", () => {
    const storage = {
        get(key) { try { return localStorage.getItem(key); } catch (error) { return null; } },
        set(key, value) { try { localStorage.setItem(key, value); } catch (error) { /* Preferences are optional. */ } },
    };
    const sidebar = document.getElementById("app-sidebar");
    const menuButton = document.querySelector("[data-sidebar-toggle]");
    const mobile = window.matchMedia("(max-width: 991.98px)");
    if (sidebar && menuButton && window.bootstrap) {
        if (storage.get("nasil.dashboard.sidebar") === "collapsed") document.body.classList.add("sidebar-collapsed");
        const updateExpanded = () => menuButton.setAttribute("aria-expanded", String(mobile.matches ? sidebar.classList.contains("show") : !document.body.classList.contains("sidebar-collapsed")));
        menuButton.addEventListener("click", () => {
            if (mobile.matches) {
                bootstrap.Offcanvas.getOrCreateInstance(sidebar).toggle();
            } else {
                document.body.classList.toggle("sidebar-collapsed");
                storage.set("nasil.dashboard.sidebar", document.body.classList.contains("sidebar-collapsed") ? "collapsed" : "expanded");
                updateExpanded();
            }
        });
        sidebar.addEventListener("shown.bs.offcanvas", updateExpanded);
        sidebar.addEventListener("hidden.bs.offcanvas", () => { updateExpanded(); if (mobile.matches) menuButton.focus(); });
        sidebar.querySelectorAll("a").forEach(link => link.addEventListener("click", () => {
            if (mobile.matches) bootstrap.Offcanvas.getInstance(sidebar)?.hide();
        }));
        mobile.addEventListener("change", () => {
            if (!mobile.matches && sidebar.classList.contains("show")) bootstrap.Offcanvas.getInstance(sidebar)?.hide();
            updateExpanded();
        });
        updateExpanded();
    }

    const themeButton = document.querySelector("[data-theme-toggle]");
    const updateThemeButton = () => {
        if (!themeButton) return;
        const dark = document.documentElement.dataset.bsTheme === "dark";
        themeButton.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
        themeButton.setAttribute("aria-pressed", String(dark));
        const icon = themeButton.querySelector("i");
        if (icon) icon.className = dark ? "bi bi-moon-stars" : "bi bi-sun";
    };
    themeButton?.addEventListener("click", () => {
        const theme = document.documentElement.dataset.bsTheme === "dark" ? "light" : "dark";
        document.documentElement.dataset.bsTheme = theme;
        storage.set("nasil.dashboard.theme", theme);
        updateThemeButton();
    });
    updateThemeButton();

    const searchModal = document.getElementById("module-search");
    const searchInput = document.getElementById("module-search-input");
    const searchResults = document.querySelector(".module-search-results");
    const searchEmpty = document.querySelector(".module-search-empty");
    if (searchModal && searchInput && searchResults && window.bootstrap) {
        const entries = [];
        document.querySelectorAll(".sidebar-nav a.sidebar-link").forEach(source => {
            const label = source.querySelector(".nav-label")?.textContent.trim();
            if (!label) return;
            const link = document.createElement("a");
            link.href = source.getAttribute("href");
            const icon = source.querySelector("i");
            if (icon) link.append(icon.cloneNode(true));
            link.append(document.createTextNode(label));
            searchResults.append(link);
            entries.push({ label: label.toLocaleLowerCase(), link });
        });
        const filterModules = () => {
            const query = searchInput.value.trim().toLocaleLowerCase();
            let visible = 0;
            entries.forEach(entry => { entry.link.hidden = !entry.label.includes(query); if (!entry.link.hidden) visible++; });
            if (searchEmpty) searchEmpty.hidden = visible > 0;
        };
        searchInput.addEventListener("input", filterModules);
        searchInput.addEventListener("keydown", event => {
            if (event.key === "Enter") {
                const first = entries.find(entry => !entry.link.hidden);
                if (first) { event.preventDefault(); first.link.click(); }
            }
        });
        searchModal.addEventListener("shown.bs.modal", () => { searchInput.value = ""; filterModules(); searchInput.focus(); });
        document.addEventListener("keydown", event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                bootstrap.Modal.getOrCreateInstance(searchModal).show();
            }
        });
    }

    document.querySelectorAll("[data-table-search]").forEach(input => {
        const table = document.getElementById(input.dataset.tableSearch);
        if (!table) return;
        const rows = [...table.querySelectorAll("tbody tr[data-record-row]")];
        const noResults = table.querySelector(".table-no-results");
        const counter = document.querySelector("[data-table-count='" + table.id + "']");
        input.addEventListener("input", () => {
            const query = input.value.trim().toLocaleLowerCase();
            let visible = 0;
            rows.forEach(row => { row.hidden = !row.textContent.toLocaleLowerCase().includes(query); if (!row.hidden) visible++; });
            if (noResults) noResults.hidden = visible > 0 || rows.length === 0;
            if (counter) counter.textContent = visible + (visible === 1 ? " record" : " records");
        });
    });

    document.querySelectorAll("[data-range-select]").forEach(select => {
        select.addEventListener("change", () => select.form?.requestSubmit());
    });
});
