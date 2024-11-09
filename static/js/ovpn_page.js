// Функция для преобразования времени в локальное, используя data-атрибуты
function convertToUserTimezone() {
    const timeCells = document.querySelectorAll('.connection-time');
    
    timeCells.forEach(cell => {
        const utcDateStr = cell.getAttribute('data-utc'); // Извлекаем значение data-utc
        if (utcDateStr) {
            const utcDate = new Date(utcDateStr); // Преобразуем строку в дату UTC
            const localDateString = utcDate.toLocaleString(); // Преобразуем в локальное время
            cell.textContent = localDateString; // Заменяем текст ячейки на локальное время
        }
    });
}

// Вызов функции после загрузки страницы
document.addEventListener('DOMContentLoaded', convertToUserTimezone);

function toggleRealIP() {
    const showRealIP = document.getElementById("toggleRealIP").checked;
    const ipCells = document.querySelectorAll(".real-ip-cell");
    
    ipCells.forEach(cell => {
        if (showRealIP) {
            // Показать реальные IP
            cell.textContent = cell.getAttribute("data-real-ip");
        } else {
            // Показать замаскированные IP
            cell.textContent = cell.getAttribute("data-masked-ip");
        }
    });
}
