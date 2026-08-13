document.addEventListener("DOMContentLoaded", () => {
    /* ===== USER DROPDOWN MENU ===== */
    const topbarUser = document.querySelector(".topbar-user");
    
    if (topbarUser) {
        topbarUser.addEventListener("click", (e) => {
            e.stopPropagation();
            topbarUser.classList.toggle("active");
        });
    }

    // Close dropdown when clicking outside
    document.addEventListener("click", () => {
        if (topbarUser && topbarUser.classList.contains("active")) {
            topbarUser.classList.remove("active");
        }
    });

    /* ===== MOBILE MENU TOGGLE ===== */
    const mobileMenuButton = document.querySelector(".mobile-menu-button");
    const sidebar = document.querySelector(".sidebar");
    const overlay = document.querySelector(".sidebar-overlay");

    const closeSidebar = () => {
        sidebar?.classList.remove("active");
        overlay?.classList.remove("show");
    };

    if (mobileMenuButton) {
        mobileMenuButton.addEventListener("click", () => {
            sidebar?.classList.toggle("active");
            overlay?.classList.toggle("show");
        });
    }

    overlay?.addEventListener("click", closeSidebar);
    
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeSidebar();
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 991) closeSidebar();
    });

    // Close sidebar when clicking on a link
    const sidebarLinks = document.querySelectorAll(".sidebar-link");
    sidebarLinks.forEach(link => {
        link.addEventListener("click", () => {
            if (window.innerWidth <= 991) {
                closeSidebar();
            }
        });
    });

    /* ===== PERIOD BUTTON DROPDOWN ===== */
    const periodButtons = document.querySelectorAll(".period-button");
    periodButtons.forEach(button => {
        button.addEventListener("click", (e) => {
            e.stopPropagation();
            const menu = button.nextElementSibling;
            if (menu) {
                menu.classList.toggle("show");
            }
        });
    });

    document.addEventListener("click", () => {
        const menus = document.querySelectorAll(".period-menu.show");
        menus.forEach(menu => menu.classList.remove("show"));
    });

});
