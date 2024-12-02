let inactivityTimeout;

function resetTimer() {
    clearTimeout(inactivityTimeout);
    inactivityTimeout = setTimeout(function() {
        // Отправить запрос на сервер для завершения сессии
        fetch('/logout', { method: 'POST' }).then(response => {
            window.location.href = '/login'; // Перенаправить на страницу входа
        });
    }, 5* 60 * 1000); // 10 секунд в миллисекундах
}

// Добавляем обработчики событий для отслеживания активности
window.onload = resetTimer;
window.onmousemove = resetTimer;
window.onkeydown = resetTimer;
window.onscroll = resetTimer;