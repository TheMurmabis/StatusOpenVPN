async function updateSystemInfo() {
    try {
        const response = await fetch('/api/system_info');
        const data = await response.json();

        // Проверяем, изменились ли данные
        const cpuElement = document.getElementById('cpu_load');
        const memoryElement = document.getElementById('memory_used');
        const diskElement = document.getElementById('disk_used');
        const networkElement = document.getElementById('network_load');
        const uptimeElement = document.getElementById('server_uptime');  

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

        // Обновление данных о сетевой загрузке
        const networkLoad = data.network_load;
        let networkHtml = '';

        for (const [interface, stats] of Object.entries(networkLoad)) {
            networkHtml += `<p><b>${interface}</b>: Передача: ${stats.sent_speed} Мбит/с, Прием: ${stats.recv_speed} Мбит/с</p>`;
        }
        // Обновляем сетевую нагрузку только если HTML изменился
        if (networkElement.innerHTML !== networkHtml) {
            networkElement.innerHTML = networkHtml;
        }

        // Обновляем uptime
        if (uptimeElement.textContent !== data.uptime) {
            uptimeElement.textContent = data.uptime;  // Обновляем текст
        }
    } catch (error) {
        console.error('Ошибка при загрузке данных:', error);
    }
}

// Автообновление 
setInterval(updateSystemInfo, 5000);

// Первоначальный вызов функции
updateSystemInfo();


