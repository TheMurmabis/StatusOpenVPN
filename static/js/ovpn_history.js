function convertToUserTimezone() {
    const timeCells = document.querySelectorAll('.connection-time');

    timeCells.forEach(cell => {
        const utcDateStr = cell.getAttribute('data-utc');
        if (utcDateStr) {
            const utcDate = new Date(utcDateStr);
            const localDateString = utcDate.toLocaleString(undefined, {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
            cell.textContent = localDateString;
        }
    });
}

document.addEventListener('DOMContentLoaded', convertToUserTimezone);
