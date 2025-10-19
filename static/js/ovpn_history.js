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

    // Фильтр
    const logFilter = document.getElementById('logFilter'); 

    logFilter.addEventListener('input', () => {
        const filterValue = logFilter.value.toLowerCase(); 

        document.querySelectorAll('.log-row').forEach(row => {
            const text = [
                '.client-name', '.real-ip', '.local-ip', '.protocol'
            ]
                .map(sel => row.querySelector(sel)?.textContent.toLowerCase() || '')
                .join(' ');

            row.style.display = text.includes(filterValue) ? '' : 'none';
        });
    });
});
