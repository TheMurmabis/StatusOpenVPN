let autoRefreshEnabled = false;
let refreshInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    const checkbox = document.getElementById('auto-refresh-toggle');

    // Восстановление состояния из localStorage
    autoRefreshEnabled = localStorage.getItem('autoRefreshEnabled') === 'true';
    checkbox.checked = autoRefreshEnabled;

    if (autoRefreshEnabled) {
        startAutoRefresh();
    }

    checkbox.addEventListener('change', () => {
        autoRefreshEnabled = checkbox.checked;
        localStorage.setItem('autoRefreshEnabled', autoRefreshEnabled);

        if (autoRefreshEnabled) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });
});

function startAutoRefresh() {
    stopAutoRefresh(); // Очистка предыдущего интервала
    refreshInterval = setInterval(updateStats, 3000);
    updateStats(); // Немедленный запуск
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

async function updateStats() {
    try {
        const response = await fetch('/api/wg/stats', {
            method: 'GET',
            headers: {
                'X-No-Session-Refresh': 'true',
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            credentials: 'same-origin'
        });

        const data = await response.json();

        data.forEach(interface => {
            const tbody = document.getElementById(`tbody-${interface.interface}`);
            if (!tbody) return;

            // Очистить старые строки
            tbody.innerHTML = '';

            interface.peers.forEach((peer, index) => {
                const tr = document.createElement('tr');
                tr.className = peer.online ? 'traffic-online' : 'traffic-offline wg_table';

                tr.innerHTML = `
                    <td>
                        <div class="d-flex flex-column align-items-center">
                            <span>
                            <small class="${peer.online ? 'text-success' : 'traffic-offline'}">
                                ${peer.online ? 'Онлайн' : 'Офлайн'}
                            </small>
                        </div>
                    </td>
                    <td title="Peer: ${peer.masked_peer}">${peer.client}</td>
                    <td class="d-none d-sm-table-cell">${peer.endpoint || 'N/A'}</td>
                    <td class="d-none d-sm-table-cell">
                        ${peer.visible_ips.map(ip => `<span>${ip}</span>`).join(', ')}
                        ${peer.hidden_ips && peer.hidden_ips.length > 0 ? `
                            <div class="hidden-ips" style="display:none;">
                                ${peer.hidden_ips.map(ip => `<span>${ip}</span>`).join(', ')}
                            </div>
                            <a href="#" class="btn btn-link p-0 small" onclick="toggleIps(${index}); return false;">
                                Показать все
                            </a>
                        ` : ''}
                    </td>
                    <td class="d-none d-sm-table-cell">${peer.latest_handshake || 'N/A'}</td>
                    <td class="d-none d-sm-table-cell">${peer.daily_received || '0.0'}</td>
                    <td class="d-none d-sm-table-cell">${peer.daily_sent || '0.0'}</td>
                    <td>${peer.received || '0.0'}</td>
                    <td>${peer.sent || '0.0'}</td>
                `;

                tbody.appendChild(tr);
            });

            // Обновить количество онлайн / всего
            const badge = tbody.closest('.table-responsive').querySelector('.badge');
            if (badge) {
                const onlineCount = interface.peers.filter(p => p.online).length;
                const totalCount = interface.peers.length;
                badge.innerHTML = `<strong> ${onlineCount}</strong> / <strong>${totalCount}</strong>`;
            }
        });
    } catch (error) {
        console.error('Ошибка при обновлении данных:', error);
    }
}

// Переключение показа скрытых IP-адресов
function toggleIps(index) {
    const rows = document.querySelectorAll(`#wg-stats-container .table-responsive`);
    rows.forEach((row, i) => {
        if (i === index) {
            const hiddenDiv = row.querySelector('.hidden-ips');
            if (hiddenDiv) {
                hiddenDiv.style.display = hiddenDiv.style.display === 'none' ? 'block' : 'none';
            }
        }
    });
}
