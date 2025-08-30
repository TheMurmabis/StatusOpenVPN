let inactivityTimeout;

function resetTimer() {
    clearTimeout(inactivityTimeout);

    if (!window.rememberMe) {  
        inactivityTimeout = setTimeout(function() {
            fetch('/logout', {
                method: 'POST',
                credentials: 'include'
            }).then(() => {
                window.location.href = '/login';
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
