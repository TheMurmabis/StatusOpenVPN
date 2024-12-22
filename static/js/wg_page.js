    function toggleIps(index) {
        var hiddenIps = document.querySelectorAll('.hidden-ips')[index - 1];
        var button = document.getElementById('toggle-btn-' + index);

        if (hiddenIps.style.display === 'none') {
            hiddenIps.style.display = 'inline';
            button.textContent = 'Свернуть';
        } else {
            hiddenIps.style.display = 'none';
            button.textContent = 'Показать все';
        }
    }