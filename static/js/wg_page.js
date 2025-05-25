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

    // Имитация клика по карточке
    document.querySelectorAll('.client-card').forEach(card => {
        card.addEventListener('click', function(e) {
            if (!e.target.closest('.icon-btn')) {
                console.log('Открываем клиента:', this.querySelector('h4').textContent);
            }
        });
    });
});

function startAutoRefresh() {
    stopAutoRefresh(); // очистим на всякий случай

    refreshInterval = setInterval(updateStats, 3000);
    updateStats(); // сразу первый раз
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

async function updateStats() {
    try {
        // const response = await fetch('/api/wg/stats');
        const response = await fetch('/api/wg/stats', {
            method: 'GET',
            headers: {
                'X-No-Session-Refresh': 'true',  // Специальный заголовок
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            },
            credentials: 'same-origin'
        });
        
        const data = await response.json();

        data.forEach(interface => {
            const container = document.querySelector(`.interface-section[data-interface="${interface.interface}"]`);
            if (!container) return;

            //Обновление количества подкюченных клиентов
            const statsElement = container.querySelector('.interface-stats');
            if (statsElement) {
                const onlineCount = interface.peers.filter(peer => peer.online).length;
                const totalCount = interface.peers.length;
                statsElement.innerHTML = `[<span title="Онлайн">${onlineCount}/</span><span title="Клиентов">${totalCount}</span>]`;
            }

            const clientGrid = container.querySelector('.client-grid');
            if (!clientGrid) return;

            clientGrid.innerHTML = '';

            interface.peers.forEach(peer => {
                const card = document.createElement('div');
                card.className = `wg-client-card card-style ${peer.online ? 'online' : 'offline'}`;

                card.innerHTML = `
                
                    <div class="client-header">
                        <div class="client-name-status">
                            <div class="status-dot ${peer.online ? 'dot-online' : 'dot-offline'}"></div>
                            <h4 class="${peer.online ? 'traffic-online' : 'traffic-offline'}">${peer.client}</h4>
                        </div>
                        <div class="client-actions ${peer.online ? 'traffic-online' : 'traffic-offline'}">
                            <i class="fas fa-user"></i>
                        </div>
                    </div>
                    <div class="client-details ${peer.online ? 'traffic-online' : 'traffic-offline'}">
                        <div class="detail-row"><span>IP-адрес:</span> ${peer.visible_ips[0] || 'N/A'}</div>
                        <div class="detail-row"><span>Реальный IP:</span>${ peer.endpoint || 'N/A' }</div>
                        <div class="detail-row"><span>${peer.online ? 'В сети: ' : 'Не в сети: '}</span> ${peer.latest_handshake || 'Нет данных'}</div>
                    </div>
                    <div class="traffic-bars">
                        <!--<div class="progress-bar">
                            <div class="progress-fill" style="width: ${peer.traffic_percentage}%; background-color: ${peer.online ? 'green' : 'gray'}"></div>
                        </div>-->
                        <div class="progress-container">
                            <div title="Получено от клиента (${ peer.received_percentage }%)" class="progress-fill ${ peer.online ? 'received-fill-online' : 'received-fill-offline'}"
                                    style="width: ${ peer.received_percentage }%;">
                            </div>
                            <div title="Передано клиенту (${ peer.sent_percentage }%)" class="progress-fill ${ peer.online ? 'sent-fill-online' : 'sent-fill-offline'}"
                                    style="width: ${ peer.sent_percentage }%;">
                            </div>
                                
                                
                        </div>
                        <div class="traffic-labels ${peer.online ? 'traffic-online' : 'traffic-offline'}">
                            <span title="Получено от клиента (${ peer.received_percentage }%)"><i class="fas fa-arrow-down"></i> ${peer.received || '0.0 '}</span>
                            <span title="Передано клиенту (${ peer.sent_percentage }%)"><i class="fas fa-arrow-up"></i> ${peer.sent || '0.0 '}</span>
                        </div>
                        <hr>

                        <div class="traffic-labels small ${peer.online ? 'traffic-online' : 'traffic-offline'}">
                            <span><i class="fas fa-calendar-day"></i> Сегодня: ↓ ${peer.daily_received}</span>
                            <span>↑ ${peer.daily_sent}</span>
                        </div>
                    </div>
                    ${peer.hidden_ips && peer.hidden_ips.length > 0 ? `
                        <details class="ip-toggle">
                            <summary>Доп. IP</summary>
                            <div class="ip-list">
                                ${peer.hidden_ips.map(ip => `<span>${ip}</span>`).join('')}
                            </div>
                        </details>
                    ` : ''}
                `;

                card.addEventListener('click', function(e) {
                    if (!e.target.closest('.icon-btn')) {
                        console.log('Открываем клиента:', peer.client);
                    }
                });

                clientGrid.appendChild(card);
            });
        });

    } catch (error) {
        console.error('Ошибка при обновлении данных:', error);
    }
}


