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

    // Получаем состояние галочки из localStorage
    var checkbox = document.getElementById("hide_undef");
    var hideUndefState = localStorage.getItem("hide_undef_state");

    // Устанавливаем состояние галочки в зависимости от сохраненного значения
    checkbox.checked = hideUndefState === "true";

    // Включаем фильтрацию в зависимости от состояния галочки
    toggleUNDEF();

    // Вызов функции для преобразования времени
    convertToUserTimezone();
});

// Функция для фильтрации строк в зависимости от состояния чекбокса
function toggleUNDEF() {
    var checkbox = document.getElementById("hide_undef");
    var rows = document.querySelectorAll(".log-row");

    // Сохраняем состояние галочки в localStorage
    localStorage.setItem("hide_undef_state", checkbox.checked);

    rows.forEach(function(row) {
        var clientName = row.querySelector("td:first-child").textContent.trim(); // Получаем текст из первого столбца (Клиент)

        // Если в столбце "Клиент" значение "UNDEF" и чекбокс установлен, скрываем строку
        if (checkbox.checked && clientName === "UNDEF") {
            row.style.display = "none";
        } else {
            row.style.display = ""; // Показываем строку, если условие не выполнено
        }
    });
}
