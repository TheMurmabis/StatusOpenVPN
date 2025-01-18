document.addEventListener("DOMContentLoaded", () => {
    // Кэширование элементов
    const showIPCheckbox = document.getElementById("show-ip-checkbox");
    const showColumnsCheckbox = document.getElementById("show-columns-checkbox");
    const speedColumns = document.querySelectorAll(".speed-column");
    const savedShowIPState = localStorage.getItem("showRealIP");
    const savedShowColumnsState = localStorage.getItem("showColumns");

    // Восстановление состояния реальных IP
    if (savedShowIPState === "true") {
        showIPCheckbox.checked = true;
        toggleRealIP(true);
    } else {
        showIPCheckbox.checked = false;
        toggleRealIP(false);
    }
    // Восстановление состояния столбцов
    if (savedShowColumnsState === "true") {
        showColumnsCheckbox.checked = true;
        toggleColumns(true);
    } else {
        showColumnsCheckbox.checked = false;
        toggleColumns(false);
    }

    // Обработчики событий
    showIPCheckbox.addEventListener("change", () => {
        toggleRealIP(showIPCheckbox.checked);
        localStorage.setItem("showRealIP", showIPCheckbox.checked);
    });

    showColumnsCheckbox.addEventListener("change", () => {
        toggleColumns(showColumnsCheckbox.checked);
        localStorage.setItem("showColumns", showColumnsCheckbox.checked);
    });

    // Функции для отображения реальных IP
    function toggleRealIP(showRealIP) {
        const ipCells = document.querySelectorAll(".real-ip-cell");
        ipCells.forEach(cell => {
            cell.textContent = showRealIP ? cell.getAttribute("data-real-ip") : cell.getAttribute("data-masked-ip");
        });
    }

    // Функции для отображения столбцов скорости
    function toggleColumns(showColumns) {
        speedColumns.forEach(column => column.classList.toggle("hidden", !showColumns));
    }

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


    // Вызов функции для преобразования времени
    convertToUserTimezone();

    // Включаем фильтрацию в зависимости от состояния галочки
    toggleUNDEF();
});

// Функция для фильтрации строк в зависимости от состояния чекбокса
function toggleUNDEF() {
    var checkbox = document.getElementById("hide_undef");
    var rows = document.querySelectorAll(".log-row");

    // Сохраняем состояние галочки в localStorage
    localStorage.setItem("hide_undef_state", checkbox.checked);

    rows.forEach(function (row) {
        var clientName = row.querySelector("td:first-child").textContent.trim(); // Получаем текст из первого столбца (Клиент)

        // Если в столбце "Клиент" значение "UNDEF" и чекбокс установлен, скрываем строку
        if (checkbox.checked && clientName === "UNDEF") {
            row.style.display = "none";
        } else {
            row.style.display = ""; // Показываем строку, если условие не выполнено
        }
    });
}
