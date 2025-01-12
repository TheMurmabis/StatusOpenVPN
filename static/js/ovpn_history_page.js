document.addEventListener("DOMContentLoaded", () => {

    // Функция для преобразования времени в локальное, используя data-атрибуты
    function convertToUserTimezone() {
        const timeCells = document.querySelectorAll('.connection-time');

        timeCells.forEach(cell => {
            const utcDateStr = cell.getAttribute('data-utc');
            if (utcDateStr) {
                const utcDate = new Date(utcDateStr);
                const localDateString = utcDate.toLocaleString();
                cell.textContent = localDateString;
            }
        });
    }

    // Вызов функции для преобразования времени
    convertToUserTimezone();
});
