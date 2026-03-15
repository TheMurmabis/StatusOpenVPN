let autoRefreshEnabled = false;
let refreshInterval = null;

// Данные для модального окна подтверждения отключения
let pendingToggle = null;

document.addEventListener("DOMContentLoaded", () => {
    const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
    const onlineOnlyToggle = document.getElementById("online-only-toggle");
    const disabledOnlyToggle = document.getElementById("disabled-only-toggle");

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
    disabledOnlyToggle.checked = localStorage.getItem("showDisabledOnly") === "true";

    // Взаимная блокировка: «Только онлайн» и «Только отключённые» несовместимы
    onlineOnlyToggle.addEventListener("change", async () => {
        if (onlineOnlyToggle.checked) {
            disabledOnlyToggle.checked = false;
            localStorage.setItem("showDisabledOnly", "false");
        }
        localStorage.setItem("showOnlineOnly", onlineOnlyToggle.checked);
        await updateStats();
        applyFilters();
    });

    disabledOnlyToggle.addEventListener("change", async () => {
        if (disabledOnlyToggle.checked) {
            onlineOnlyToggle.checked = false;
            localStorage.setItem("showOnlineOnly", "false");
        }
        localStorage.setItem("showDisabledOnly", disabledOnlyToggle.checked);
        await updateStats();
        applyFilters();
    });

    // Кнопка подтверждения в модальном окне
    document.getElementById("confirmDisableBtn").addEventListener("click", () => {
        const modal = bootstrap.Modal.getInstance(document.getElementById("confirmDisableModal"));
        modal.hide();

        if (pendingToggle) {
            executePeerToggle(pendingToggle.element, pendingToggle.peer, pendingToggle.iface, pendingToggle.clientName, false);
            pendingToggle = null;
        }
    });

    // Отмена модального окна — возвращаем toggle
    document.getElementById("confirmDisableModal").addEventListener("hidden.bs.modal", () => {
        if (pendingToggle) {
            pendingToggle.element.checked = true;
            pendingToggle = null;
        }
    });

    updateStats().then(() => {
        applyFilters();
        document.getElementById("wg-stats-container").style.visibility = "visible";
    });
});

function startAutoRefresh() {
    stopAutoRefresh();
    refreshInterval = setInterval(async () => {
        await updateStats();
        applyFilters();
    }, 3000);
    updateStats().then(applyFilters);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

async function updateStats() {
    try {
        const response = await fetch("${basePath}/api/wg/stats", {
            method: "GET",
            headers: {
                "X-No-Session-Refresh": "true",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache"
            },
            credentials: "same-origin"
        });

        const data = await response.json();

        data.forEach(iface => {
            const tbody = document.getElementById(`tbody-${iface.interface}`);
            if (!tbody) return;

            tbody.innerHTML = "";

            iface.peers.forEach((peer, index) => {
                const tr = document.createElement("tr");
                const isEnabled = peer.enabled !== false;
                tr.className = !isEnabled ? "traffic-disabled wg_table" : (peer.online ? "traffic-online" : "traffic-offline wg_table");

                tr.innerHTML = `
                    <td>
                        <label class="switch mb-0">
                            <input type="checkbox" class="peer-toggle"
                                   data-peer="${peer.peer}"
                                   data-interface="${iface.interface}"
                                   data-client="${peer.client || 'Unknown'}"
                                   ${isEnabled ? 'checked' : ''}>
                            <span class="slider round"></span>
                        </label>
                    </td>
                    <td>
                        <div class="d-flex flex-column align-items-center">
                            <span>
                            <small class="${!isEnabled ? 'text-muted' : (peer.online ? 'text-success' : 'traffic-offline')}">
                                ${!isEnabled ? 'Отключён' : (peer.online ? 'Онлайн' : 'Офлайн')}
                            </small>
                        </div>
                    </td>
                    <td title="Peer: ${peer.masked_peer}">${peer.client}</td>
                    <td>${peer.endpoint || 'N/A'}</td>
                    <td>
                        ${(peer.visible_ips || []).map(ip => `<span>${ip}</span>`).join(', ')}
                        ${peer.hidden_ips && peer.hidden_ips.length > 0 ? `
                            <div class="hidden-ips" style="display:none;">
                                ${peer.hidden_ips.map(ip => `<span>${ip}</span>`).join(', ')}
                            </div>
                            <a href="#" class="btn btn-link p-0 small" onclick="toggleIps(${index}); return false;">
                                Показать все
                            </a>
                        ` : ''}
                    </td>
                    <td>${peer.latest_handshake || 'N/A'}</td>
                    <td>${peer.daily_received || '0.0'}</td>
                    <td>${peer.daily_sent || '0.0'}</td>
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


function applyFilters() {
    const showOnlyOnline = document.getElementById("online-only-toggle").checked;
    const showOnlyDisabled = document.getElementById("disabled-only-toggle").checked;
    const tables = document.querySelectorAll("#wg-stats-container .table-responsive");
    const noClientsCard = document.getElementById("no-active-clients");

    let anyVisibleClients = false;

    tables.forEach(table => {
        const rows = table.querySelectorAll("tbody tr");
        let onlineCount = 0;
        let totalCount = rows.length;
        let visibleCount = 0;

        rows.forEach(row => {
            const isOnline = row.classList.contains("traffic-online");
            const isDisabled = row.classList.contains("traffic-disabled");
            if (isOnline) onlineCount++;

            let visible = true;
            if (showOnlyOnline && !isOnline) visible = false;
            if (showOnlyDisabled && !isDisabled) visible = false;

            row.style.display = visible ? "" : "none";
            if (visible) visibleCount++;
        });

        const badge = table.querySelector(".badge");
        if (badge) {
            badge.innerHTML = `<strong>${onlineCount}</strong> / <strong>${totalCount}</strong>`;
        }

        table.style.display = visibleCount === 0 && (showOnlyOnline || showOnlyDisabled) ? "none" : "";

        if (visibleCount > 0) anyVisibleClients = true;
    });

    if ((showOnlyOnline || showOnlyDisabled) && !anyVisibleClients) {
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

// Переключение включён/отключён для пира
document.addEventListener("change", async (e) => {
    if (!e.target.classList.contains("peer-toggle")) return;

    const toggle = e.target;
    const peer = toggle.dataset.peer;
    const iface = toggle.dataset.interface;
    const clientName = toggle.dataset.client;
    const enable = toggle.checked;

    if (!enable) {
        // Отключение — показываем подтверждение
        pendingToggle = { element: toggle, peer, iface, clientName };
        document.getElementById("confirmClientName").textContent = clientName;
        const modal = new bootstrap.Modal(document.getElementById("confirmDisableModal"));
        modal.show();
        return;
    }

    // Включение — сразу выполняем
    executePeerToggle(toggle, peer, iface, clientName, true);
});

async function executePeerToggle(toggle, peer, iface, clientName, enable) {
    toggle.disabled = true;

    try {
        const response = await fetch("${basePath}/api/wg/peer/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ peer, interface: iface, enable, client_name: clientName }),
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || "Ошибка переключения");
        }

        setTimeout(async () => {
            await updateStats();
            applyFilters();
            toggle.disabled = false;
        }, 1500);
    } catch (error) {
        console.error("Ошибка переключения пира:", error);
        toggle.checked = !enable;
        toggle.disabled = false;
    }
}
