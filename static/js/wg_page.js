let autoRefreshEnabled = false;
let refreshInterval = null;

document.addEventListener("DOMContentLoaded", () => {
    const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
    const onlineOnlyToggle = document.getElementById("online-only-toggle");

    autoRefreshEnabled = localStorage.getItem("autoRefreshEnabled") === "true";
    autoRefreshToggle.checked = autoRefreshEnabled;
    if (autoRefreshEnabled) startAutoRefresh();

    autoRefreshToggle.addEventListener("change", () => {
        autoRefreshEnabled = autoRefreshToggle.checked;
        localStorage.setItem("autoRefreshEnabled", autoRefreshEnabled);
        if (autoRefreshEnabled) startAutoRefresh();
        else stopAutoRefresh();
    });

    onlineOnlyToggle.checked = localStorage.getItem("showOnlineOnly") === "true";

    // Применяем фильтр сразу при загрузке, чтобы убрать моргание
    updateStats().then(() => {
        applyOnlineFilter();
        document.getElementById("wg-stats-container").style.visibility = "visible";
    });

    // Слушаем изменения чекбокса
    onlineOnlyToggle.addEventListener("change", async () => {
        localStorage.setItem("showOnlineOnly", onlineOnlyToggle.checked);
        await updateStats(); // обновляем данные
        applyOnlineFilter(); // применяем фильтр
    });
});

function startAutoRefresh() {
    stopAutoRefresh();
    refreshInterval = setInterval(async () => {
        await updateStats();
        applyOnlineFilter();
    }, 3000);
    updateStats().then(applyOnlineFilter);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

async function updateStats() {
    try {
        const basePath = window.basePath || '';
        const response = await fetch(`${basePath}/api/wg/stats`, {
            method: "GET",
            headers: {
                "X-No-Session-Refresh": "true",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache"
            },
            credentials: "same-origin"
        });

        const data = await response.json();

        data.forEach(interface => {
            const tbody = document.getElementById(`tbody-${interface.interface}`);
            if (!tbody) return;

            tbody.innerHTML = "";

            interface.peers.forEach((peer, index) => {
                const tr = document.createElement("tr");
                tr.className = peer.online ? "traffic-online" : "traffic-offline wg_table";

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
                    <td >${peer.endpoint || 'N/A'}</td>
                    <td >
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
                    <td >${peer.latest_handshake || 'N/A'}</td>
                    <td >${peer.daily_received || '0.0'}</td>
                    <td >${peer.daily_sent || '0.0'}</td>
                    <td>${peer.received || '0.0'}</td>
                    <td>${peer.sent || '0.0'}</td>
                `;

                tbody.appendChild(tr);
            });
        });
    } catch (error) {
        console.error("Ошибка при обновлении данных:", error);
    }
}


function applyOnlineFilter() {
    const onlineOnlyToggle = document.getElementById("online-only-toggle");
    const showOnlyOnline = onlineOnlyToggle.checked;
    const tables = document.querySelectorAll("#wg-stats-container .table-responsive");
    const noClientsCard = document.getElementById("no-active-clients");

    let anyOnlineClients = false;

    tables.forEach(table => {
        const rows = table.querySelectorAll("tbody tr");
        let onlineCount = 0;
        let totalCount = rows.length;

        rows.forEach(row => {
            const isOnline = row.classList.contains("traffic-online");
            if (showOnlyOnline && !isOnline) row.style.display = "none";
            else row.style.display = "";
            if (isOnline) onlineCount++;
        });

        // Обновляем бейдж
        const badge = table.querySelector(".badge");
        if (badge) {
            badge.innerHTML = `<strong>${onlineCount}</strong> / <strong>${totalCount}</strong>`;
        }

        // Скрываем интерфейс без онлайн-клиентов
        table.style.display = showOnlyOnline && onlineCount === 0 ? "none" : "";

        if (onlineCount > 0) anyOnlineClients = true;
    });

    // Показ плашки «Нет активных подключений»
    if (showOnlyOnline && !anyOnlineClients) {
        noClientsCard.classList.add("show");
    } else {
        noClientsCard.classList.remove("show");
    }
}

// Переключение показа скрытых IP-адресов
function toggleIps(index) {
    const rows = document.querySelectorAll("#wg-stats-container .table-responsive");
    rows.forEach((row, i) => {
        if (i === index) {
            const hiddenDiv = row.querySelector(".hidden-ips");
            if (hiddenDiv) {
                hiddenDiv.style.display = hiddenDiv.style.display === "none" ? "block" : "none";
            }
        }
    });
}
