let autoRefreshEnabled = false;
let refreshInterval = null;

let pendingMenuDisable = null;

function wgIfaceDisplay(iface) {
    if (!iface) return "";
    const s = String(iface);
    const l = s.toLowerCase();
    if (l === "vpn") return s.toUpperCase();
    return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

function escapeAttr(s) {
    return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/</g, "&lt;");
}

function resolveApiUrl(path) {
    if (!path) return "";
    if (path.startsWith("http://") || path.startsWith("https://")) return path;
    const bp = typeof window.basePath === "string" ? window.basePath : "";
    let p = path.startsWith("/") ? path : `/${path}`;
    if (!bp) return p;
    if (p === bp || p.startsWith(`${bp}/`)) return p;
    return `${bp}${p}`;
}

function absoluteApiUrl(pathFromFlask) {
    const p = resolveApiUrl(pathFromFlask);
    if (!p) return "";
    if (p.startsWith("http://") || p.startsWith("https://")) return p;
    try {
        return new URL(p, window.location.origin).href;
    } catch (e) {
        return p;
    }
}

function initWgRowDropdowns(tbody) {
    tbody.querySelectorAll(".ovpn-actions-menu-btn").forEach((el) => {
        if (typeof bootstrap !== "undefined" && bootstrap.Dropdown) {
            bootstrap.Dropdown.getOrCreateInstance(el, {
                popperConfig(defaultBsPopperConfig) {
                    return { ...defaultBsPopperConfig, strategy: "fixed" };
                },
            });
        }
    });
}

/** Не перерисовывать таблицу по таймеру, пока открыто меню действий или модалка — иначе DOM меню уничтожается (tbody.innerHTML). */
function wgAutoRefreshPaused() {
    const root = document.getElementById("wg-stats-container");
    if (!root) return true;
    if (document.body.classList.contains("modal-open")) return true;
    if (root.querySelector('.ovpn-actions-menu-btn[aria-expanded="true"]')) return true;
    return false;
}

function buildWgActionsCell(peer, ifaceName, isEnabled) {
    const client = peer.client || "Unknown";
    const ifaceDisp = wgIfaceDisplay(ifaceName);
    const peerAttr = escapeAttr(peer.peer);
    const ifaceAttr = escapeAttr(ifaceName);
    const clientAttr = escapeAttr(client);

    let toggleBlock;
    if (!isEnabled) {
        toggleBlock = `
            <li>
                <button type="button"
                    class="dropdown-item d-flex align-items-center gap-2 btn-action wg-client-action-btn ovpn-action-item--neutral"
                    data-action="enable" data-peer="${peerAttr}"
                    data-interface="${ifaceAttr}" data-client="${clientAttr}">
                    <i class="fa fa-unlock fa-fw" aria-hidden="true"></i>
                    <span class="wg-action-label">Включить (${escapeAttr(ifaceDisp)})</span>
                </button>
            </li>`;
    } else {
        toggleBlock = `
            <li>
                <button type="button"
                    class="dropdown-item d-flex align-items-center gap-2 btn-action wg-client-action-btn text-danger"
                    data-action="disable" data-peer="${peerAttr}"
                    data-interface="${ifaceAttr}" data-client="${clientAttr}">
                    <i class="fa fa-ban fa-fw" aria-hidden="true"></i>
                    <span class="wg-action-label">Отключить (${escapeAttr(ifaceDisp)})</span>
                </button>
            </li>`;
    }

    return `
        <td class="text-center actions-cell">
            <div class="dropdown ovpn-actions-dropdown d-inline-block">
                <button type="button" class="btn btn-sm btn-light border ovpn-actions-menu-btn"
                    data-bs-toggle="dropdown" data-bs-container="body" aria-expanded="false"
                    title="Действия" aria-label="Меню действий">
                    <i class="fa fa-ellipsis-v" aria-hidden="true"></i>
                </button>
                <ul class="dropdown-menu dropdown-menu-end ovpn-actions-menu shadow-sm">
                    ${toggleBlock}
                    <li><hr class="dropdown-divider"></li>
                    <li>
                        <button type="button"
                            class="dropdown-item d-flex align-items-center gap-2 btn-action btn-download-config ovpn-action-item--neutral wg-client-action-btn"
                            data-action="download-config" data-client="${clientAttr}">
                            <i class="fa fa-download fa-fw" aria-hidden="true"></i>
                            <span class="wg-action-label">Скачать конфигурацию</span>
                        </button>
                    </li>
                </ul>
            </div>
        </td>`;
}

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

    document.getElementById("confirmDisableBtn").addEventListener("click", () => {
        const modal = bootstrap.Modal.getInstance(document.getElementById("confirmDisableModal"));
        modal?.hide();
        if (pendingMenuDisable) {
            const { btn, peer, iface, clientName } = pendingMenuDisable;
            pendingMenuDisable = null;
            wgExecuteToggle(peer, iface, clientName, false, btn);
        }
    });

    document.getElementById("confirmDisableModal").addEventListener("hidden.bs.modal", () => {
        pendingMenuDisable = null;
    });

    document.getElementById("wg-stats-container").addEventListener("click", (e) => {
        const btn = e.target.closest(".wg-client-action-btn");
        if (!btn) return;

        const action = btn.dataset.action;
        const peer = btn.dataset.peer;
        const iface = btn.dataset.interface;
        const clientName = btn.dataset.client || "";

        if (action === "download-config") {
            openWgConfigModal(clientName);
            return;
        }
        if (action === "enable") {
            wgExecuteToggle(peer, iface, clientName, true, btn);
            return;
        }
        if (action === "disable") {
            pendingMenuDisable = { btn, peer, iface, clientName };
            document.getElementById("confirmClientName").textContent = clientName;
            bootstrap.Modal.getOrCreateInstance(document.getElementById("confirmDisableModal")).show();
        }
    });

    const wgDownloadBtn = document.getElementById("wgConfigDownloadBtn");
    if (wgDownloadBtn) {
        wgDownloadBtn.addEventListener("click", () => {
            runWgConfigDownload().catch((e) => {
                console.error(e);
                alert(e.message || "Ошибка скачивания");
            });
        });
    }

    const wgStatsRoot = document.getElementById("wg-stats-container");
    wgStatsRoot.addEventListener("hidden.bs.dropdown", () => {
        if (!autoRefreshEnabled) return;
        if (wgAutoRefreshPaused()) return;
        updateStats().then(applyFilters);
    });

    updateStats().then(() => {
        applyFilters();
        wgStatsRoot.style.visibility = "visible";
    });
});

function startAutoRefresh() {
    stopAutoRefresh();
    refreshInterval = setInterval(async () => {
        if (wgAutoRefreshPaused()) return;
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

async function wgExecuteToggle(peer, iface, clientName, enable, btn) {
    const api = window.wgApi;
    const labelEl = btn && btn.querySelector(".wg-action-label");
    const originalText = labelEl ? labelEl.textContent : btn ? btn.textContent : "";
    if (btn) {
        btn.disabled = true;
        if (labelEl) labelEl.textContent = "…";
        else btn.textContent = "…";
    }

    const url = absoluteApiUrl(api && api.peerToggle);
    if (!url) {
        if (btn) {
            btn.disabled = false;
            if (labelEl) labelEl.textContent = originalText;
            else btn.textContent = originalText;
        }
        return;
    }

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                peer,
                interface: iface,
                enable,
                client_name: clientName,
            }),
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || "Ошибка переключения");
        }

        await updateStats();
        applyFilters();
    } catch (e) {
        console.error(e);
        alert(e.message || "Ошибка при выполнении запроса");
    } finally {
        if (btn) {
            btn.disabled = false;
            if (labelEl) labelEl.textContent = originalText;
            else btn.textContent = originalText;
        }
    }
}

async function updateStats() {
    const bp = typeof window.basePath === "string" ? window.basePath : "";
    try {
        const response = await fetch(`${bp}/api/wg/stats`, {
            method: "GET",
            headers: {
                "X-No-Session-Refresh": "true",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
            },
            credentials: "same-origin",
        });

        const data = await response.json();

        data.forEach((iface) => {
            const tbody = document.getElementById(`tbody-${iface.interface}`);
            if (!tbody) return;

            tbody.innerHTML = "";

            iface.peers.forEach((peer, index) => {
                const tr = document.createElement("tr");
                const isEnabled = peer.enabled !== false;
                tr.className = !isEnabled
                    ? "traffic-disabled wg_table"
                    : peer.online
                      ? "traffic-online"
                      : "traffic-offline wg_table";

                tr.innerHTML = `
                    <td class="text-center vpn-table-client" title="Peer: ${peer.masked_peer}">${peer.client}</td>
                    <td>
                        <div class="d-flex flex-column align-items-center">
                            <small class="${!isEnabled ? "text-muted" : peer.online ? "text-success" : "traffic-offline"}">
                                ${!isEnabled ? "Отключён" : peer.online ? "Онлайн" : "Офлайн"}
                            </small>
                        </div>
                    </td>
                    <td>${peer.endpoint || "N/A"}</td>
                    <td>
                        ${(peer.visible_ips || []).map((ip) => `<span>${ip}</span>`).join(", ")}
                        ${peer.hidden_ips && peer.hidden_ips.length > 0
                            ? `
                            <div class="hidden-ips" style="display:none;">
                                ${peer.hidden_ips.map((ip) => `<span>${ip}</span>`).join(", ")}
                            </div>
                            <a href="#" class="btn btn-link p-0 small" onclick="toggleIps(${index}); return false;">
                                Показать все
                            </a>
                        `
                            : ""}
                    </td>
                    <td>${peer.latest_handshake || "N/A"}</td>
                    <td>${peer.daily_received || "0.0"}</td>
                    <td>${peer.daily_sent || "0.0"}</td>
                    <td>${peer.received || "0.0"}</td>
                    <td>${peer.sent || "0.0"}</td>
                    ${buildWgActionsCell(peer, iface.interface, isEnabled)}
                `;

                tbody.appendChild(tr);
            });

            initWgRowDropdowns(tbody);
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

    tables.forEach((table) => {
        const rows = table.querySelectorAll("tbody tr");
        let onlineCount = 0;
        let totalCount = rows.length;
        let visibleCount = 0;

        rows.forEach((row) => {
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

let wgDownloadState = { clientName: "", items: [], index: 0 };

function buildWgDownloadHref(clientName, index) {
    const api = window.wgApi;
    if (!api || !api.clientConfigDownload) return "";
    const base = absoluteApiUrl(api.clientConfigDownload);
    if (!base) return "";
    const u = new URL(base);
    u.searchParams.set("client_name", clientName);
    u.searchParams.set("index", String(index));
    return u.toString();
}

async function runWgConfigDownload() {
    const { clientName, items, index } = wgDownloadState;
    const url = buildWgDownloadHref(clientName, index);
    if (!url) {
        alert("Не удалось сформировать ссылку скачивания.");
        return;
    }
    const idx = Number(index);
    const meta = items.find((it) => Number(it.index) === idx) || items[idx] || {};
    const filename = meta.filename || "wireguard.conf";

    const r = await fetch(url, { credentials: "same-origin" });
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    if (!r.ok) {
        if (ct.includes("application/json")) {
            const d = await r.json().catch(() => ({}));
            throw new Error(d.message || `Ошибка ${r.status}`);
        }
        throw new Error(`Ошибка ${r.status}`);
    }
    if (ct.includes("application/json")) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.message || "Сервер вернул JSON вместо файла");
    }

    const blob = await r.blob();
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(u);
}

function openWgConfigModal(clientName) {
    const api = window.wgApi;
    if (!api || !api.clientConfig || !api.clientConfigDownload) return;

    const modalElCfg = document.getElementById("wgConfigDownloadModal");
    const loadingEl = document.getElementById("wgConfigDownloadLoading");
    const bodyEl = document.getElementById("wgConfigDownloadBody");
    const selectEl = document.getElementById("wgConfigProfileSelect");
    const profileSelectLabel = document.querySelector('label[for="wgConfigProfileSelect"]');

    if (!modalElCfg || !loadingEl || !bodyEl || !selectEl) return;

    loadingEl.classList.remove("d-none");
    bodyEl.classList.add("d-none");
    selectEl.classList.add("d-none");
    selectEl.innerHTML = "";
    if (profileSelectLabel) profileSelectLabel.classList.add("d-none");

    const listBase = absoluteApiUrl(api.clientConfig);
    if (!listBase) {
        loadingEl.classList.add("d-none");
        alert("Не задан URL API конфигурации.");
        return;
    }
    const listUrl = new URL(listBase);
    listUrl.searchParams.set("client_name", clientName);

    fetch(listUrl.toString(), { credentials: "same-origin" })
        .then((r) => {
            if (!r.ok) {
                return r.json().then((d) => {
                    throw new Error(d.message || `HTTP ${r.status}`);
                });
            }
            return r.json();
        })
        .then(async (data) => {
            loadingEl.classList.add("d-none");
            if (!data.success) {
                alert(data.message || "Не удалось получить список профилей.");
                return;
            }
            const items = data.items || [];
            if (items.length === 0) {
                alert("Не найдено файлов .conf для этого клиента.");
                return;
            }

            wgDownloadState = { clientName, items, index: items[0].index };

            if (items.length === 1) {
                try {
                    await runWgConfigDownload();
                } catch (e) {
                    console.error(e);
                    alert(e.message || "Ошибка скачивания");
                }
                return;
            }

            bodyEl.classList.remove("d-none");
            selectEl.classList.remove("d-none");
            if (profileSelectLabel) profileSelectLabel.classList.remove("d-none");

            items.forEach((it) => {
                const opt = document.createElement("option");
                opt.value = String(it.index);
                opt.textContent = it.label || `Профиль ${it.index}`;
                selectEl.appendChild(opt);
            });
            selectEl.value = String(items[0].index);

            selectEl.onchange = () => {
                const idx = parseInt(selectEl.value, 10);
                wgDownloadState.index = idx;
            };

            wgDownloadState.index = items[0].index;
            bootstrap.Modal.getOrCreateInstance(modalElCfg).show();
        })
        .catch((e) => {
            console.error(e);
            loadingEl.classList.add("d-none");
            alert(e.message || "Ошибка при запросе списка профилей.");
        });
}
