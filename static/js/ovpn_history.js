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
