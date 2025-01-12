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

document.addEventListener('DOMContentLoaded', function () {
    const checkbox = document.getElementById('auto-refresh-toggle');

    // Восстановление состояния из localStorage
    const isChecked = localStorage.getItem('autoRefreshEnabled') === 'true';
    checkbox.checked = isChecked;

    let autoRefreshEnabled = isChecked;  // Синхронизируем с чекбоксом

    // Сохранение состояния при изменении
    checkbox.addEventListener('change', function () {
        localStorage.setItem('autoRefreshEnabled', checkbox.checked);
        autoRefreshEnabled = checkbox.checked;  // Обновляем переменную
    });

    // Функция обновления
    async function updateStats() {
        if (!autoRefreshEnabled) return;  // Проверка состояния

        try {
            const response = await fetch('/api/wg/stats');
            const data = await response.json();

            data.forEach(interface => {
                const tableBody = document.querySelector(`#tbody-${interface.interface}`);
                if (!tableBody) return;

                tableBody.innerHTML = '';

                interface.peers.forEach(peer => {
                    const row = document.createElement('tr');

                    const statusCell = document.createElement('td');
                    const statusIndicator = document.createElement('div');
                    statusIndicator.classList.add('text-center', 'status-indicator', peer.online ? 'online' : 'offline');
                    statusCell.appendChild(statusIndicator);

                    const statusText = document.createElement('span');
                    statusText.classList.add(peer.online ? 'online-text' : 'offline-text');
                    statusText.textContent = peer.online ? 'В сети' : 'Не в сети';
                    statusCell.appendChild(statusText);
                    row.appendChild(statusCell);

                    const clientCell = document.createElement('td');
                    clientCell.classList.add('text-center');
                    clientCell.textContent = peer.client;
                    row.appendChild(clientCell);

                    const peerCell = document.createElement('td');
                    peerCell.classList.add('text-center');
                    peerCell.textContent = peer.masked_peer;
                    row.appendChild(peerCell);

                    const endpointCell = document.createElement('td');
                    endpointCell.classList.add('text-center');
                    endpointCell.textContent = peer.endpoint || 'N/A';
                    row.appendChild(endpointCell);

                    const ipCell = document.createElement('td');
                    ipCell.classList.add('text-center');
                    ipCell.textContent = peer.visible_ips.join(', ') || 'N/A';
                    row.appendChild(ipCell);

                    const handshakeCell = document.createElement('td');
                    handshakeCell.classList.add('text-center');
                    handshakeCell.textContent = peer.latest_handshake || 'N/A';
                    row.appendChild(handshakeCell);

                    const receivedCell = document.createElement('td');
                    receivedCell.classList.add('text-center');
                    receivedCell.textContent = peer.received || 'N/A';
                    row.appendChild(receivedCell);

                    const sentCell = document.createElement('td');
                    sentCell.classList.add('text-center');
                    sentCell.textContent = peer.sent || 'N/A';
                    row.appendChild(sentCell);

                    tableBody.appendChild(row);
                });
            });

        } catch (error) {
            console.error('Ошибка при загрузке данных:', error);
        }
    }

    // Автообновление каждую секунду
    setInterval(updateStats, 1000);

    // Первоначальный вызов
    updateStats();
});
