(function () {
    let feedbackTimer = null;

    function showCopyMessage(message, success) {
        let status = document.getElementById('appCopyFeedback');
        if (!status) {
            status = document.createElement('div');
            status.id = 'appCopyFeedback';
            status.className = 'app-copy-feedback';
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
            document.body.appendChild(status);
        }
        status.textContent = message;
        status.classList.toggle('is-error', !success);
        status.classList.add('show');
        window.clearTimeout(feedbackTimer);
        feedbackTimer = window.setTimeout(() => status.classList.remove('show'), 2200);
    }

    function fallbackCopy(text) {
        const area = document.createElement('textarea');
        area.value = text;
        area.setAttribute('readonly', '');
        area.className = 'app-copy-fallback-field';
        document.body.appendChild(area);
        area.select();
        area.setSelectionRange(0, area.value.length);
        let copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (_) {
            copied = false;
        }
        area.remove();
        return copied;
    }

    function setButtonFeedback(button, success) {
        if (!button) return;
        const icon = button.querySelector('i');
        if (!button.dataset.copyOriginalTitle) {
            button.dataset.copyOriginalTitle = button.title || 'Скопировать ссылку';
            button.dataset.copyOriginalLabel = button.getAttribute('aria-label') || button.title;
        }
        if (icon && !button.dataset.copyOriginalIcon) {
            button.dataset.copyOriginalIcon = icon.className;
        }

        window.clearTimeout(button._copyFeedbackTimer);
        button.classList.toggle('is-copy-success', success);
        button.classList.toggle('is-copy-error', !success);
        const message = success ? 'Ссылка скопирована' : 'Не удалось скопировать ссылку';
        button.title = message;
        button.setAttribute('aria-label', message);
        if (icon) icon.className = success ? 'fa fa-check' : 'fa fa-triangle-exclamation';

        button._copyFeedbackTimer = window.setTimeout(() => {
            button.classList.remove('is-copy-success', 'is-copy-error');
            button.title = button.dataset.copyOriginalTitle || 'Скопировать ссылку';
            button.setAttribute(
                'aria-label',
                button.dataset.copyOriginalLabel || 'Скопировать ссылку'
            );
            if (icon && button.dataset.copyOriginalIcon) {
                icon.className = button.dataset.copyOriginalIcon;
            }
        }, 2200);
    }

    window.copyTextWithFeedback = async function (text, button) {
        if (!text) return false;
        let copied = false;
        if (navigator.clipboard && window.isSecureContext) {
            try {
                await navigator.clipboard.writeText(text);
                copied = true;
            } catch (_) {
                copied = fallbackCopy(text);
            }
        } else {
            copied = fallbackCopy(text);
        }
        setButtonFeedback(button, copied);
        showCopyMessage(
            copied ? 'Ссылка скопирована' : 'Не удалось скопировать ссылку',
            copied
        );
        return copied;
    };
})();

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
    const closeBtn = document.getElementById('appSidebarCloseBtn');
    const mainWrap = document.querySelector('.app-main-wrap');
    const bottomNav = document.querySelector('.app-bottom-nav');
    const groupToggles = Array.from(sidebar.querySelectorAll('[data-sidebar-group-toggle]'));
    let drawerPreviouslyFocused = null;


    const mqDesktop = window.matchMedia('(min-width: 992px)');

    function isDesktop() {
        return mqDesktop.matches;
    }

    function setDrawerOpen(open, returnFocus = true) {
        const wasOpen = shell.classList.contains('app-shell--mobile-drawer-open');
        if (open) {
            drawerPreviouslyFocused = document.activeElement;
            shell.classList.add('app-shell--mobile-drawer-open');
            sidebar.setAttribute('aria-hidden', 'false');
            if (openBtn) openBtn.setAttribute('aria-expanded', 'true');
            if (backdrop) {
                backdrop.setAttribute('aria-hidden', 'false');
            }
            if (!isDesktop()) {
                document.documentElement.classList.add('app-shell--lock-scroll');
                if (mainWrap) mainWrap.inert = true;
                if (bottomNav) bottomNav.inert = true;
                requestAnimationFrame(function () {
                    if (closeBtn) closeBtn.focus();
                });
            }
        } else {
            shell.classList.remove('app-shell--mobile-drawer-open');
            if (openBtn) openBtn.setAttribute('aria-expanded', 'false');
            if (mainWrap) mainWrap.inert = false;
            if (bottomNav) bottomNav.inert = false;
            if (wasOpen && returnFocus && drawerPreviouslyFocused && typeof drawerPreviouslyFocused.focus === 'function') {
                drawerPreviouslyFocused.focus();
            }
            sidebar.setAttribute('aria-hidden', isDesktop() ? 'false' : 'true');
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
        openBtn.setAttribute('aria-expanded', 'false');
        openBtn.setAttribute('aria-controls', 'appSidebar');
        openBtn.addEventListener('click', function () {
            setDrawerOpen(true);
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            setDrawerOpen(false);
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
                setDrawerOpen(false, false);
            }
        });
    });

    groupToggles.forEach(function (button) {
        button.addEventListener('click', function () {
            const panelId = button.getAttribute('aria-controls');
            const panel = panelId ? document.getElementById(panelId) : null;
            const group = button.closest('.app-sidebar__group');
            if (!panel || !group) return;
            const willOpen = panel.hidden;

            groupToggles.forEach(function (otherButton) {
                if (otherButton === button) return;
                const otherPanelId = otherButton.getAttribute('aria-controls');
                const otherPanel = otherPanelId ? document.getElementById(otherPanelId) : null;
                const otherGroup = otherButton.closest('.app-sidebar__group');
                if (otherPanel) otherPanel.hidden = true;
                if (otherGroup) otherGroup.classList.remove('is-open');
                otherButton.setAttribute('aria-expanded', 'false');
            });

            panel.hidden = !willOpen;
            group.classList.toggle('is-open', willOpen);
            button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            try {
                localStorage.setItem('statusAppSidebarOpenGroup', willOpen ? panelId : '');
            } catch (_) { /* ignore */ }
        });
    });

    if (!sidebar.querySelector('.app-sidebar__group .app-sidebar__link.active')) {
        try {
            const savedPanelId = localStorage.getItem('statusAppSidebarOpenGroup');
            const savedToggle = savedPanelId
                ? sidebar.querySelector('[data-sidebar-group-toggle][aria-controls="' + savedPanelId + '"]')
                : null;
            const savedPanel = savedPanelId ? document.getElementById(savedPanelId) : null;
            const savedGroup = savedToggle ? savedToggle.closest('.app-sidebar__group') : null;
            if (savedToggle && savedPanel && savedGroup) {
                savedPanel.hidden = false;
                savedGroup.classList.add('is-open');
                savedToggle.setAttribute('aria-expanded', 'true');
            }
        } catch (_) { /* ignore */ }
    }

    mqDesktop.addEventListener('change', function () {
        setDrawerOpen(false);
        applyFromStorage();
    });

    applyFromStorage();
    markLayoutReady();
    sidebar.setAttribute('aria-hidden', isDesktop() ? 'false' : 'true');

    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && shell.classList.contains('app-shell--mobile-drawer-open')) {
            setDrawerOpen(false);
        }
        if (ev.key === 'Tab' && !isDesktop() && shell.classList.contains('app-shell--mobile-drawer-open')) {
            const focusable = Array.from(sidebar.querySelectorAll(
                'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )).filter(function (element) {
                return !element.closest('[hidden]');
            });
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (ev.shiftKey && document.activeElement === first) {
                ev.preventDefault();
                last.focus();
            } else if (!ev.shiftKey && document.activeElement === last) {
                ev.preventDefault();
                first.focus();
            }
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

(function () {
    const button = document.getElementById('appNotificationsButton');
    const badge = document.getElementById('appNotificationsBadge');
    const list = document.getElementById('appNotificationsList');
    const markReadButton = document.getElementById('appNotificationsMarkRead');
    if (!button || !badge || !list || !markReadButton) return;

    const STORAGE_KEY = 'statusAppReadNotifications';
    let items = [];
    let loading = false;
    const markAllOnLoad = button.dataset.markAllOnLoad === 'true';

    function readLegacySeen() {
        try {
            const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
            return new Set(Array.isArray(value) ? value.filter((key) => typeof key === 'string') : []);
        } catch (_) {
            return new Set();
        }
    }

    async function markAsRead(keys, markAll = false) {
        const uniqueKeys = Array.from(new Set(keys.filter(Boolean)));
        if (!markAll && !uniqueKeys.length) return true;
        try {
            const basePath = window.basePath || '';
            const response = await fetch(`${basePath}/api/notifications`, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                },
                credentials: 'same-origin',
                body: JSON.stringify(markAll ? { all: true } : { keys: uniqueKeys }),
            });
            if (!response.ok) return false;
            const data = await response.json();
            if (!data.success) return false;
            const marked = new Set(markAll ? items.map((item) => item.key) : uniqueKeys);
            items.forEach((item) => {
                if (marked.has(item.key)) item.read = true;
            });
            return true;
        } catch (_) {
            return false;
        }
    }

    function formatTime(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '';
        return date.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
        });
    }

    function updateBadge() {
        const unread = items.filter((item) => !item.read).length;
        badge.textContent = unread > 99 ? '99+' : String(unread);
        badge.classList.toggle('d-none', unread === 0);
        button.setAttribute('aria-label', unread ? `Уведомления: ${unread} новых` : 'Уведомления');
    }

    function render() {
        list.textContent = '';
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'small text-muted text-center p-3';
            empty.textContent = 'Новых событий нет';
            list.appendChild(empty);
            updateBadge();
            return;
        }
        items.forEach((item) => {
            const row = document.createElement('div');
            row.className = 'app-notifications__item d-flex gap-2 px-3 py-2';
            if (!item.read) row.classList.add('is-unread');
            row.setAttribute('role', 'button');
            row.setAttribute('tabindex', '0');
            row.setAttribute('aria-label', `Отметить прочитанным: ${item.title || 'Событие'}`);

            const markItemRead = async () => {
                if (item.read) return;
                if (await markAsRead([item.key])) render();
            };
            row.addEventListener('click', markItemRead);
            row.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    markItemRead();
                }
            });

            const icon = document.createElement('i');
            icon.className = `bi bi-${item.icon || 'bell'} app-notifications__icon text-${item.level || 'secondary'}`;
            icon.setAttribute('aria-hidden', 'true');

            const content = document.createElement('div');
            content.className = 'min-w-0 flex-grow-1';
            const title = document.createElement('div');
            title.className = 'small fw-semibold';
            title.textContent = item.title || 'Событие';
            content.appendChild(title);
            if (item.details) {
                const details = document.createElement('div');
                details.className = 'small text-muted text-truncate';
                details.textContent = item.details;
                details.title = item.details;
                content.appendChild(details);
            }
            const time = document.createElement('div');
            time.className = 'app-notifications__time';
            time.textContent = formatTime(item.timestamp);
            content.appendChild(time);
            row.append(icon, content);
            list.appendChild(row);
        });
        updateBadge();
    }

    async function loadNotifications() {
        if (loading || document.visibilityState === 'hidden') return;
        loading = true;
        try {
            const basePath = window.basePath || '';
            const response = await fetch(`${basePath}/api/notifications`, {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
            });
            if (!response.ok) return;
            const data = await response.json();
            items = Array.isArray(data.items) ? data.items : [];

            const legacySeen = readLegacySeen();
            const legacyKeys = items
                .filter((item) => legacySeen.has(item.key) && !item.read)
                .map((item) => item.key);
            if (legacySeen.size) {
                const migrated = !legacyKeys.length || await markAsRead(legacyKeys);
                if (migrated) {
                    try { localStorage.removeItem(STORAGE_KEY); } catch (_) { /* ignore */ }
                }
            }
            if (markAllOnLoad) {
                await markAsRead([], true);
            }
            render();
        } catch (_) {
            // Уведомления не должны мешать работе интерфейса.
        } finally {
            loading = false;
        }
    }

    markReadButton.addEventListener('click', async () => {
        if (await markAsRead([], true)) render();
    });
    button.addEventListener('shown.bs.dropdown', loadNotifications);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') loadNotifications();
    });
    loadNotifications();
    window.setInterval(loadNotifications, 60000);
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
