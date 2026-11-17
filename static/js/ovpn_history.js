document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.connection-time[data-utc]').forEach(cell => {
        const utcDate = new Date(cell.dataset.utc);
        cell.textContent = utcDate.toLocaleString(undefined, {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    });

    const toggleGroup = (row) => {
        const key = row.dataset.historyKey;
        if (!key) {
            return;
        }

        const open = row.classList.toggle('is-open');
        row.setAttribute('aria-expanded', open ? 'true' : 'false');
        document.querySelectorAll(`.ovpn-history-session[data-history-parent="${key}"]`).forEach((sessionRow) => {
            sessionRow.classList.toggle('d-none', !open);
        });
    };

    document.querySelectorAll('.ovpn-history-group--expandable').forEach((row) => {
        row.addEventListener('click', (event) => {
            if (event.target.closest('a')) {
                return;
            }
            toggleGroup(row);
        });

        row.addEventListener('keydown', (event) => {
            if (event.key !== 'Enter' && event.key !== ' ') {
                return;
            }
            event.preventDefault();
            toggleGroup(row);
        });
    });

    const logFilter = document.getElementById('logFilter');
    if (!logFilter) {
        return;
    }

    const currentQuery = (logFilter.dataset.currentQuery || '').trim();
    let debounceId = null;

    const applyFilter = () => {
        const value = logFilter.value.trim();
        if (value === currentQuery) {
            return;
        }

        const url = new URL(window.location.href);
        if (value) {
            url.searchParams.set('q', value);
        } else {
            url.searchParams.delete('q');
        }
        url.searchParams.set('page', '1');
        window.location.href = url.toString();
    };

    logFilter.addEventListener('input', () => {
        if (debounceId) {
            clearTimeout(debounceId);
        }
        debounceId = setTimeout(applyFilter, 400);
    });

    logFilter.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') {
            return;
        }
        event.preventDefault();
        if (debounceId) {
            clearTimeout(debounceId);
        }
        applyFilter();
    });
});
