(function () {
    const shell = document.getElementById('appShell');
    const sidebar = document.getElementById('appSidebar');
    const backdrop = document.getElementById('appSidebarBackdrop');
    if (!shell || !sidebar) {
        return;
    }

    const LS_COLLAPSED = 'statusAppSidebarCollapsed';

    const toggleSidebarBtn = document.getElementById('appSidebarToggleBtn');
    const openBtn = document.getElementById('appSidebarOpenBtn');


    const mqDesktop = window.matchMedia('(min-width: 992px)');

    function isDesktop() {
        return mqDesktop.matches;
    }

    function setDrawerOpen(open) {
        if (open) {
            shell.classList.add('app-shell--mobile-drawer-open');
            if (backdrop) {
                backdrop.setAttribute('aria-hidden', 'false');
            }
            if (!isDesktop()) {
                document.documentElement.classList.add('app-shell--lock-scroll');
            }
        } else {
            shell.classList.remove('app-shell--mobile-drawer-open');
            if (backdrop) {
                backdrop.setAttribute('aria-hidden', 'true');
            }
            document.documentElement.classList.remove('app-shell--lock-scroll');
        }
    }

    function updateToggleIcons() {
        const collapsed = shell.classList.contains('app-shell--sidebar-collapsed');
        const expanded = !collapsed;

        if (toggleSidebarBtn) {
            toggleSidebarBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            const collapseLabel = toggleSidebarBtn.querySelector('.app-sidebar__collapse-label');
            if (collapseLabel) {
                collapseLabel.textContent = expanded ? 'Свернуть' : 'Развернуть';
            }
        }
    }

    function applyFromStorage() {
        const collapsed = localStorage.getItem(LS_COLLAPSED) === '1';

        if (collapsed && isDesktop()) {
            shell.classList.add('app-shell--sidebar-collapsed');
        } else {
            shell.classList.remove('app-shell--sidebar-collapsed');
        }
        updateToggleIcons();
    }

    function markLayoutReady() {
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                shell.classList.add('app-shell--sidebar-layout-ready');
            });
        });
    }

    function toggleCollapse() {
        if (!isDesktop()) {
            return;
        }
        shell.classList.toggle('app-shell--sidebar-collapsed');
        localStorage.setItem(
            LS_COLLAPSED,
            shell.classList.contains('app-shell--sidebar-collapsed') ? '1' : '0'
        );
        updateToggleIcons();
    }

    const githubBtn = document.querySelector('[data-app-github-open]');
    if (githubBtn) {
        githubBtn.addEventListener('click', function () {
            window.open(
                'https://github.com/TheMurmabis/StatusOpenVPN',
                '_blank',
                'noopener,noreferrer'
            );
        });
    }

    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', toggleCollapse);
    }
    if (openBtn) {
        openBtn.addEventListener('click', function () {
            setDrawerOpen(true);
        });
    }

    if (backdrop) {
        backdrop.addEventListener('click', function () {
            setDrawerOpen(false);
        });
    }

    sidebar.querySelectorAll('a[href]').forEach(function (link) {
        link.addEventListener('click', function () {
            if (!isDesktop()) {
                setDrawerOpen(false);
            }
        });
    });

    mqDesktop.addEventListener('change', function () {
        setDrawerOpen(false);
        applyFromStorage();
    });

    applyFromStorage();
    markLayoutReady();

    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && shell.classList.contains('app-shell--mobile-drawer-open')) {
            setDrawerOpen(false);
        }
    });
})();

(function () {
    const panel = document.getElementById('appTopbarFiltersPanel');
    const btn = document.getElementById('appTopbarFiltersToggle');
    if (!panel || !btn) {
        return;
    }

    const mqDesktop = window.matchMedia('(min-width: 992px)');

    function collapseFiltersForMobile() {
        if (mqDesktop.matches) {
            panel.classList.remove('show');
            btn.classList.remove('active');
            btn.setAttribute('aria-expanded', 'false');
        }
    }

    btn.addEventListener('click', function () {
        if (mqDesktop.matches) {
            return;
        }
        const open = panel.classList.toggle('show');
        btn.classList.toggle('active', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    mqDesktop.addEventListener('change', collapseFiltersForMobile);
    collapseFiltersForMobile();
})();

let inactivityTimeout;

function resetTimer() {
    clearTimeout(inactivityTimeout);

    if (!window.rememberMe) {
        inactivityTimeout = setTimeout(function () {
            const basePath = window.basePath || '';
            fetch(basePath + '/logout', {
                method: 'POST',
                credentials: 'include',
            }).then(() => {
                window.location.href = basePath + '/login';
            });
        }, 5 * 60 * 1000); // 5 минут
    }
}

// Добавляем обработчики только если rememberMe = false
if (!window.rememberMe) {
    window.onload = resetTimer;
    window.onmousemove = resetTimer;
    window.onkeydown = resetTimer;
    window.onscroll = resetTimer;
}
