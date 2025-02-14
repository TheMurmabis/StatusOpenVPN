async function updateSystemInfo() {
    try {
        const response = await fetch('/api/system_info');
        const data = await response.json();

        // Получаем элементы
        const cpuElement = document.getElementById('cpu_load');
        const memoryElement = document.getElementById('memory_used');
        const diskElement = document.getElementById('disk_used');
        const networkElement = document.getElementById('network_load');
        const uptimeElement = document.getElementById('server_uptime');
        const interfaceElement = document.getElementById('network_interface');
        const rxElement = document.getElementById('rx_bytes');
        const txElement = document.getElementById('tx_bytes');

        // Обновляем только если данные изменились
        if (cpuElement.textContent !== data.cpu_load) {
            cpuElement.textContent = data.cpu_load;
        }
        if (memoryElement.textContent !== data.memory_used) {
            memoryElement.textContent = data.memory_used;
        }
        if (diskElement.textContent !== data.disk_used) {
            diskElement.textContent = data.disk_used;
        }
        if (uptimeElement.textContent !== data.uptime) {
            uptimeElement.textContent = data.uptime;
        }

        // Обновление сетевой информации
        if (interfaceElement.textContent !== data.network_interface) {
            interfaceElement.textContent = data.network_interface;
        }
        if (rxElement.textContent !== data.rx_bytes.toLocaleString()) {
            rxElement.textContent = data.rx_bytes.toLocaleString();
        }
        if (txElement.textContent !== data.tx_bytes.toLocaleString()) {
            txElement.textContent = data.tx_bytes.toLocaleString();
        }

        // Обновляем сетевую нагрузку
        let networkHtml = '';
        for (const [interface, stats] of Object.entries(data.network_load)) {
            networkHtml += `<p><b>${interface}</b>: Передача: ${stats.sent_speed} Мбит/с, Прием: ${stats.recv_speed} Мбит/с</p>`;
        }
        if (networkElement.innerHTML !== networkHtml) {
            networkElement.innerHTML = networkHtml;
        }
    } catch (error) {
        console.error('Ошибка при загрузке данных:', error);
    }
}

// Автообновление 
setInterval(updateSystemInfo, 5000);

// Первоначальный вызов функции
updateSystemInfo();
