let autoRefreshEnabled = false;
let refreshInterval = null;

let pendingMenuDisable = null;
let pendingWgDelete = null;
let wgRenameState = { oldName: "", iface: "", btn: null };

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

function wgAutoRefreshPaused() {
    const root = document.getElementById("wg-stats-container");
    if (!root) return true;
    return document.body.classList.contains("modal-open");
}

function buildWgActionIconBtn({ action, title, iconClass, extraClass = "", attrs = "" }) {
    return `<button type="button" class="vpn-action-icon-btn wg-client-action-btn ${extraClass}" data-action="${action}" ${attrs} title="${title}" aria-label="${title}"><i class="${iconClass}" aria-hidden="true"></i></button>`;
}

function buildWgActionsCell(peer, ifaceName, isEnabled) {
    const client = peer.client || "Unknown";
    const ifaceDisp = wgIfaceDisplay(ifaceName);
    const peerAttr = escapeAttr(peer.peer);
    const ifaceAttr = escapeAttr(ifaceName);
    const clientAttr = escapeAttr(client);
    const clientAttrs = `data-client="${clientAttr}"`;
    const toggleAttrs = `data-peer="${peerAttr}" data-interface="${ifaceAttr}" data-client="${clientAttr}"`;

    const toggleBtn = isEnabled
        ? buildWgActionIconBtn({
            action: "disable",
            title: `Отключить (${escapeAttr(ifaceDisp)})`,
            iconClass: "fa fa-ban",
            extraClass: "is-danger",
            attrs: toggleAttrs,
        })
        : buildWgActionIconBtn({
            action: "enable",
            title: `Включить (${escapeAttr(ifaceDisp)})`,
            iconClass: "fa fa-unlock",
            attrs: toggleAttrs,
        });

    return `
        <td class="text-center actions-cell">
            <div class="vpn-actions-row">
                ${buildWgActionIconBtn({
                    action: "download-config",
                    title: "QR-код",
                    iconClass: "bi bi-qr-code",
                    attrs: `${clientAttrs} data-open-qr="true"`,
                })}
                ${buildWgActionIconBtn({
                    action: "download-config",
                    title: "Скачать конфигурацию",
                    iconClass: "fa fa-download",
                    attrs: clientAttrs,
                })}
                ${buildWgActionIconBtn({
                    action: "rename",
                    title: "Переименовать",
                    iconClass: "fa fa-pencil",
                    attrs: `${clientAttrs} data-interface="${ifaceAttr}"`,
                })}
                ${toggleBtn}
                ${buildWgActionIconBtn({
                    action: "delete-client",
                    title: "Удалить клиента",
                    iconClass: "fa fa-trash",
                    extraClass: "is-danger",
                    attrs: clientAttrs,
                })}
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

    document.getElementById("wgDeleteClientConfirmBtn")?.addEventListener("click", () => {
        const modalEl = document.getElementById("wgDeleteClientModal");
        const modal = modalEl ? bootstrap.Modal.getInstance(modalEl) : null;
        if (modal) {
            modal.hide();
        }
        if (pendingWgDelete) {
            const { clientName, btn } = pendingWgDelete;
            pendingWgDelete = null;
            deleteWgClient(clientName, btn);
        }
    });

    document.getElementById("wgDeleteClientModal")?.addEventListener("hidden.bs.modal", () => {
        pendingWgDelete = null;
    });

    document.getElementById("wgRenameSubmitBtn")?.addEventListener("click", async () => {
        await submitWgRename();
    });

    document.getElementById("wgRenameModal")?.addEventListener("hidden.bs.modal", () => {
        wgRenameState = { oldName: "", iface: "", btn: null };
        const currentNameEl = document.getElementById("wgRenameCurrentName");
        const newInput = document.getElementById("wgRenameNewName");
        if (currentNameEl) currentNameEl.textContent = "";
        if (newInput) newInput.value = "";
    });

    document.getElementById("wgConfigDownloadModal")?.addEventListener("hidden.bs.modal", () => {
        resetWgConfigModal();
    });

    document.getElementById("wg-stats-container").addEventListener("click", (e) => {
        const btn = e.target.closest(".wg-client-action-btn");
        if (!btn) return;

        const action = btn.dataset.action;
        const peer = btn.dataset.peer;
        const iface = btn.dataset.interface;
        const clientName = btn.dataset.client || "";

        if (action === "download-config") {
            openWgConfigModal(clientName, { openQr: btn.dataset.openQr === "true" });
            return;
        }
        if (action === "rename") {
            openWgRenameModal(clientName, iface, btn);
            return;
        }
        if (action === "delete-client") {
            openWgDeleteModal(clientName, btn);
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

    setupWgCreateClient();

    const wgDownloadBtn = document.getElementById("wgConfigDownloadBtn");
    if (wgDownloadBtn) {
        wgDownloadBtn.addEventListener("click", () => {
            runWgConfigDownload().catch((e) => {
                console.error(e);
                alert(e.message || "Ошибка скачивания");
            });
        });
    }

    const wgQrBtn = document.getElementById("wgConfigQrBtn");
    if (wgQrBtn) {
        wgQrBtn.addEventListener("click", () => {
            if (wgDownloadState.qrOpen) {
                hideWgQrPanel();
                return;
            }
            showWgQrPanel();
        });
    }

    const wgStatsRoot = document.getElementById("wg-stats-container");

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

function openWgRenameModal(clientName, iface, btn) {
    const modalEl = document.getElementById("wgRenameModal");
    const newInput = document.getElementById("wgRenameNewName");
    const currentNameEl = document.getElementById("wgRenameCurrentName");
    if (!modalEl || !newInput || !currentNameEl) return;

    wgRenameState = {
        oldName: (clientName || "").trim(),
        iface: (iface || "").trim().toLowerCase(),
        btn: btn || null,
    };
    newInput.value = "";
    currentNameEl.textContent = wgRenameState.oldName;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
    setTimeout(() => {
        newInput.focus();
        newInput.select();
    }, 100);
}

async function submitWgRename() {
    const api = window.wgApi || {};
    const submitBtn = document.getElementById("wgRenameSubmitBtn");
    const newInput = document.getElementById("wgRenameNewName");
    const modalEl = document.getElementById("wgRenameModal");
    if (!submitBtn || !newInput || !modalEl) return;

    const oldName = (wgRenameState.oldName || "").trim();
    const newName = (newInput.value || "").trim();
    const strictNameRegex = /^[A-Za-z0-9_-]{1,32}$/;
    if (!oldName || !newName) {
        alert("Имя клиента не может быть пустым.");
        return;
    }
    if (!strictNameRegex.test(newName)) {
        alert("Некорректное имя. Используйте только латиницу, цифры, _ и - (до 32 символов).");
        return;
    }
    if (oldName === newName) {
        alert("Новое имя совпадает со старым.");
        return;
    }
    if (newName.includes("/") || newName.includes("\\") || newName.includes("\x00")) {
        alert("Недопустимое имя клиента.");
        return;
    }

    const url = absoluteApiUrl(api.clientRename);
    if (!url) {
        alert("Не задан URL переименования.");
        return;
    }

    const oldText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Переименование...";
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                old_name: oldName,
                new_name: newName,
                interface: wgRenameState.iface || "",
            }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || "Ошибка переименования");
        }

        bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        await updateStats();
        applyFilters();
    } catch (e) {
        console.error(e);
        alert(e.message || "Ошибка переименования");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = oldText;
    }
}

function openWgDeleteModal(clientName, btn) {
    const modalEl = document.getElementById("wgDeleteClientModal");
    const nameEl = document.getElementById("wgDeleteClientName");
    if (!modalEl || !nameEl) return;

    pendingWgDelete = {
        clientName: (clientName || "").trim(),
        btn: btn || null,
    };
    nameEl.textContent = pendingWgDelete.clientName;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

async function deleteWgClient(clientName, btn) {
    const api = window.wgApi || {};
    const url = absoluteApiUrl(api.clientDelete);
    if (!url) {
        alert("API удаления клиента недоступен.");
        return;
    }

    if (btn) btn.disabled = true;

    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ client_name: clientName }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.message || "Не удалось удалить клиента.");
        }

        await updateStats();
        applyFilters();
    } catch (e) {
        console.error(e);
        alert(e.message || "Ошибка при удалении клиента");
    } finally {
        if (btn) btn.disabled = false;
    }
}

let wgCreateResultClient = null;

function setupWgCreateClient() {
    const createBtn = document.getElementById("wgCreateClientBtn");
    const modalEl = document.getElementById("wgCreateClientModal");
    const nameInput = document.getElementById("wgCreateClientName");
    const submitBtn = document.getElementById("wgCreateClientSubmit");
    const resultModalEl = document.getElementById("wgCreateResultModal");
    const resultMessageEl = document.getElementById("wgCreateResultMessage");
    const resultDownloadBtn = document.getElementById("wgCreateResultDownloadBtn");

    if (createBtn && modalEl) {
        createBtn.addEventListener("click", () => {
            if (nameInput) nameInput.value = "";
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
            if (nameInput) setTimeout(() => nameInput.focus(), 200);
        });
    }

    if (submitBtn) {
        submitBtn.addEventListener("click", async () => {
            await submitWgCreateClient(nameInput, submitBtn, modalEl, resultModalEl, resultMessageEl);
        });
    }

    if (nameInput) {
        nameInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                submitBtn?.click();
            }
        });
    }

    if (resultDownloadBtn && resultModalEl) {
        resultDownloadBtn.addEventListener("click", () => {
            if (!wgCreateResultClient) return;
            const inst = bootstrap.Modal.getInstance(resultModalEl);
            if (inst) inst.hide();
            openWgConfigModal(wgCreateResultClient);
        });
    }
}

async function submitWgCreateClient(nameInput, submitBtn, modalEl, resultModalEl, resultMessageEl) {
    const api = window.wgApi || {};
    const url = absoluteApiUrl(api.clientCreate);
    if (!url) {
        alert("API создания клиента недоступен.");
        return;
    }

    const name = (nameInput ? nameInput.value : "").trim();
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(name)) {
        alert("Некорректное имя. Используйте латиницу, цифры, _ и - (до 32 символов).");
        return;
    }

    const oldText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Выполняется…";
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ client_name: name }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error((data.message || "Не удалось создать клиента.").replace(/<[^>]+>/g, ""));
        }

        wgCreateResultClient = data.client_name || name;
        if (modalEl) {
            const inst = bootstrap.Modal.getInstance(modalEl);
            if (inst) inst.hide();
        }
        if (resultMessageEl) resultMessageEl.innerHTML = data.message || "Клиент создан.";
        if (resultModalEl) bootstrap.Modal.getOrCreateInstance(resultModalEl).show();

        await updateStats();
        applyFilters();
    } catch (e) {
        console.error(e);
        alert(e.message || "Ошибка при выполнении запроса.");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = oldText;
    }
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

async function wgExecuteToggle(peer, iface, clientName, enable, btn) {
    const api = window.wgApi;
    if (btn) btn.disabled = true;

    const url = absoluteApiUrl(api && api.peerToggle);
    if (!url) {
        if (btn) btn.disabled = false;
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
        if (btn) btn.disabled = false;
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

            const isWarp = iface.interface.toLowerCase() === "warp";

            iface.peers.forEach((peer, index) => {
                const tr = document.createElement("tr");
                const isEnabled = peer.enabled !== false;
                tr.className = !isEnabled
                    ? "client-blocked wg_table"
                    : peer.online
                      ? "traffic-online"
                      : "traffic-offline wg_table";

                const clientName = peer.client || "Unknown";

                tr.innerHTML = `
                    <td class="text-center vpn-table-client" title="Peer: ${peer.masked_peer}">${escapeAttr(clientName)}</td>
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
                    ${isWarp ? '<td class="text-center actions-cell"></td>' : buildWgActionsCell(peer, iface.interface, isEnabled)}
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
    const sections = document.querySelectorAll("#wg-stats-container .dash-panel");
    const noClientsCard = document.getElementById("no-active-clients");
    const createClientBtn = document.getElementById("wgCreateClientBtn");
    const filtersActive = showOnlyOnline || showOnlyDisabled;

    let anyVisibleClients = false;

    sections.forEach((section) => {
        const table = section.querySelector(".table-responsive");
        if (!table) return;
        const rows = table.querySelectorAll("tbody tr");
        let onlineCount = 0;
        let totalCount = rows.length;
        let visibleCount = 0;

        rows.forEach((row) => {
            const isOnline = row.classList.contains("traffic-online");
            const isDisabled = row.classList.contains("client-blocked");
            if (isOnline) onlineCount++;

            let visible = true;
            if (showOnlyOnline && !isOnline) visible = false;
            if (showOnlyDisabled && !isDisabled) visible = false;

            row.style.display = visible ? "" : "none";
            if (visible) visibleCount++;
        });

        const badge = section.querySelector(".badge");
        if (badge) {
            badge.innerHTML = `<strong>${onlineCount}</strong> / <strong>${totalCount}</strong>`;
        }

        section.style.display = filtersActive && visibleCount === 0 ? "none" : "";

        if (visibleCount > 0) anyVisibleClients = true;
    });

    const showNoClientsCard = filtersActive && !anyVisibleClients;
    if (showNoClientsCard) {
        noClientsCard.classList.add("show");
    } else {
        noClientsCard.classList.remove("show");
    }
    if (createClientBtn) {
        createClientBtn.classList.toggle("d-none", showNoClientsCard);
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

let wgDownloadState = { clientName: "", items: [], index: 0, qrOpen: false };

function parseWgProfile(label) {
    const raw = String(label || "").trim();
    const parts = raw.split(" · ").map((p) => p.trim());
    const parent = (parts[0] || "").toLowerCase();
    const kindRaw = (parts[1] || "").toLowerCase();
    const rest = raw.toLowerCase();

    let group = "other";
    if (parent === "antizapret" || rest.startsWith("antizapret")) {
        group = "antizapret";
    } else if (parent === "vpn" || rest.startsWith("vpn")) {
        group = "vpn";
    }

    let kind = "other";
    if (kindRaw === "amneziawg" || rest.includes("amnezia")) {
        kind = "amnezia";
    } else if (kindRaw === "wireguard" || rest.includes("wireguard")) {
        kind = "wireguard";
    }

    return { group, kind };
}

function wgProfileTitle(profile) {
    if (profile === "antizapret") return "Antizapret";
    if (profile === "vpn") return "VPN";
    return "";
}

function wgKindTitle(kind) {
    if (kind === "amnezia") return "AmneziaWG";
    if (kind === "wireguard") return "WireGuard";
    return "";
}

function wgAppDownloadLink(href, label) {
    return `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer" class="text-decoration-none">${escapeAttr(label)}</a>`;
}

function wgDisposeAppLinkDropdowns(root) {
    if (!root || typeof bootstrap === "undefined" || !bootstrap.Dropdown) return;
    root.querySelectorAll('[data-bs-toggle="dropdown"]').forEach((el) => {
        const inst = bootstrap.Dropdown.getInstance(el);
        if (inst) inst.dispose();
    });
}

function wgAppPlatformMenu(app) {
    const items = app.links
        .map(
            (item) =>
                `<li><a class="dropdown-item" href="${escapeAttr(item.href)}" target="_blank" rel="noopener noreferrer">${escapeAttr(item.label)}</a></li>`
        )
        .join("");
    return `<span class="dropdown d-inline">
        <button type="button" class="btn btn-link p-0 align-baseline text-decoration-none wg-app-platform-toggle dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false" aria-haspopup="true">${escapeAttr(app.label)}</button>
        <ul class="dropdown-menu wg-app-platform-menu shadow-sm">${items}</ul>
    </span>`;
}

function wgAppLinkMeta(kind) {
    if (kind === "amnezia") {
        return {
            label: "AmneziaWG",
            links: [
                { href: "https://play.google.com/store/apps/details?id=org.amnezia.awg", label: "Android" },
                { href: "https://apps.apple.com/app/amneziawg/id6478942365", label: "iOS" },
                { href: "https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest", label: "Windows" },
            ],
        };
    }
    if (kind === "wireguard") {
        return {
            label: "WireGuard",
            links: [
                { href: "https://www.wireguard.com/install/", label: "WireGuard" },
            ],
        };
    }
    return null;
}

function updateWgConfigSummary(profile, kind, fallbackLabel) {
    const summaryEl = document.getElementById("wgConfigSelectionSummary");
    const appLinks = document.getElementById("wgConfigAppLinks");
    const profileText = wgProfileTitle(profile);
    const kindText = wgKindTitle(kind);
    if (summaryEl) {
        if (profileText && kindText) {
            summaryEl.textContent = `${profileText} · ${kindText}`;
        } else {
            summaryEl.textContent = fallbackLabel || "";
        }
    }
    if (!appLinks) return;
    wgDisposeAppLinkDropdowns(appLinks);
    const app = wgAppLinkMeta(kind);
    if (app && app.links.length === 1) {
        appLinks.innerHTML = ` ${wgAppDownloadLink(app.links[0].href, app.label)}`;
        return;
    }
    if (app && app.links.length > 1) {
        appLinks.innerHTML = ` ${wgAppPlatformMenu(app)}`;
        const toggle = appLinks.querySelector('[data-bs-toggle="dropdown"]');
        if (toggle && typeof bootstrap !== "undefined" && bootstrap.Dropdown) {
            bootstrap.Dropdown.getOrCreateInstance(toggle, {
                popperConfig(defaultBsPopperConfig) {
                    return { ...defaultBsPopperConfig, strategy: "fixed" };
                },
            });
        }
        return;
    }
    appLinks.innerHTML = "";
}

function setWgQrButtonLabel(open) {
    const btn = document.getElementById("wgConfigQrBtn");
    if (!btn) return;
    btn.innerHTML = '<i class="bi bi-qr-code" aria-hidden="true"></i>';
    btn.setAttribute("aria-label", open ? "Скрыть QR-код" : "Показать QR-код");
}

function hideWgQrPanel() {
    const panel = document.getElementById("wgConfigQrPanel");
    if (panel) panel.classList.add("d-none");
    wgDownloadState.qrOpen = false;
    setWgQrButtonLabel(false);
}

function showWgQrPanel() {
    const panel = document.getElementById("wgConfigQrPanel");
    if (!panel) return;
    const { clientName, index } = wgDownloadState;
    if (!clientName) return;
    panel.classList.remove("d-none");
    wgDownloadState.qrOpen = true;
    setWgQrButtonLabel(true);
    loadWgConfigQr(clientName, index).catch((e) => {
        console.error(e);
        setWgQrUiState("unavailable", e.message || "Не удалось сгенерировать QR-код.");
    });
}

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

function buildWgQrHref(clientName, index) {
    const api = window.wgApi;
    if (!api || !api.clientConfigQr) return "";
    const base = absoluteApiUrl(api.clientConfigQr);
    if (!base) return "";
    const u = new URL(base);
    u.searchParams.set("client_name", clientName);
    u.searchParams.set("index", String(index));
    return u.toString();
}

function buildWgStatsHref(clientName) {
    const api = window.wgApi || {};
    const base = absoluteApiUrl(api.statsPage);
    if (!base || !clientName) return "";
    const u = new URL(base, window.location.origin);
    u.searchParams.set("client", clientName);
    return u.pathname + u.search;
}

function setWgQrUiState(state, message) {
    const img = document.getElementById("wgConfigQrImage");
    const loadingEl = document.getElementById("wgConfigQrLoading");
    const unavailableEl = document.getElementById("wgConfigQrUnavailable");
    const errorEl = document.getElementById("wgConfigQrError");

    if (loadingEl) loadingEl.classList.toggle("d-none", state !== "loading");
    if (unavailableEl) unavailableEl.classList.toggle("d-none", state !== "unavailable");
    if (img) img.classList.toggle("d-none", state !== "ready");

    if (errorEl) {
        if (state === "unavailable" && message) {
            errorEl.textContent = message;
            errorEl.classList.remove("d-none");
        } else {
            errorEl.classList.add("d-none");
            errorEl.textContent = "";
        }
    }
}

function resetWgConfigModal() {
    wgDownloadState = { clientName: "", items: [], index: 0, qrOpen: false };
    const img = document.getElementById("wgConfigQrImage");
    const loadingEl = document.getElementById("wgConfigDownloadLoading");
    const bodyEl = document.getElementById("wgConfigDownloadBody");
    const errorEl = document.getElementById("wgConfigDownloadError");
    const selectEl = document.getElementById("wgConfigProfileSelect");
    const profileSelectLabel = document.querySelector('label[for="wgConfigProfileSelect"]');
    const profileWrap = document.getElementById("wgProfileTypeWrap");
    const kindWrap = document.getElementById("wgClientTypeWrap");

    if (img) {
        if (img._prevUrl) {
            URL.revokeObjectURL(img._prevUrl);
            img._prevUrl = null;
        }
        img.removeAttribute("src");
    }
    if (loadingEl) loadingEl.classList.remove("d-none");
    if (bodyEl) bodyEl.classList.add("d-none");
    if (errorEl) {
        errorEl.classList.add("d-none");
        errorEl.textContent = "";
    }
    if (selectEl) {
        selectEl.className = "d-none";
        selectEl.setAttribute("tabindex", "-1");
        selectEl.setAttribute("aria-hidden", "true");
        selectEl.innerHTML = "";
        selectEl.onchange = null;
    }
    if (profileSelectLabel) profileSelectLabel.classList.add("d-none");
    if (profileWrap) profileWrap.classList.remove("d-none");
    if (kindWrap) kindWrap.classList.remove("d-none");
    updateWgConfigSummary("", "", "");
    hideWgQrPanel();
    setWgQrUiState("loading");
}

async function loadWgConfigQr(clientName, index) {
    const img = document.getElementById("wgConfigQrImage");
    if (!img) return;

    setWgQrUiState("loading");

    const url = buildWgQrHref(clientName, index);
    if (!url) {
        throw new Error("Не задан URL API QR-кода.");
    }

    const r = await fetch(url, { credentials: "same-origin" });
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    if (!r.ok || ct.includes("application/json")) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.message || `Ошибка ${r.status}`);
    }

    const blob = await r.blob();
    if (img._prevUrl) URL.revokeObjectURL(img._prevUrl);
    img._prevUrl = URL.createObjectURL(blob);
    img.src = img._prevUrl;
    setWgQrUiState("ready");
}

function openWgConfigModal(clientName, options) {
    const api = window.wgApi;
    if (!api || !api.clientConfig || !api.clientConfigDownload || !api.clientConfigQr) return;
    const openQrOnReady = Boolean(options && options.openQr);

    const modalElCfg = document.getElementById("wgConfigDownloadModal");
    const loadingEl = document.getElementById("wgConfigDownloadLoading");
    const bodyEl = document.getElementById("wgConfigDownloadBody");
    const errorEl = document.getElementById("wgConfigDownloadError");
    const clientLabelEl = document.getElementById("wgConfigDownloadClient");
    const selectEl = document.getElementById("wgConfigProfileSelect");
    const profileSelectLabel = document.querySelector('label[for="wgConfigProfileSelect"]');
    const profileWrap = document.getElementById("wgProfileTypeWrap");
    const kindWrap = document.getElementById("wgClientTypeWrap");
    const profileButtons = Array.from(
        document.querySelectorAll("#wgProfileType [data-profile]")
    );
    const kindButtons = Array.from(
        document.querySelectorAll("#wgClientType [data-kind]")
    );

    if (!modalElCfg || !loadingEl || !bodyEl || !selectEl) return;

    function showDownloadError(message) {
        loadingEl.classList.add("d-none");
        bodyEl.classList.add("d-none");
        if (!errorEl) return;
        errorEl.textContent = message;
        errorEl.classList.remove("d-none");
    }

    if (clientLabelEl) clientLabelEl.textContent = clientName || "";
    resetWgConfigModal();
    if (clientLabelEl) clientLabelEl.textContent = clientName || "";
    bootstrap.Modal.getOrCreateInstance(modalElCfg).show();

    let selectedProfile = null;
    let selectedKind = null;

    function setButtonState(buttons, activeValue, dataKey) {
        buttons.forEach((btn) => {
            const active = btn.dataset[dataKey] === activeValue;
            btn.classList.toggle("active", active);
            btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
    }

    function getMatchingOption(profile, kind) {
        return Array.from(selectEl.options).find(
            (opt) => opt.dataset.profile === profile && opt.dataset.kind === kind
        );
    }

    function getAvailableKinds(profile) {
        return Array.from(selectEl.options)
            .filter((opt) => opt.dataset.profile === profile)
            .map((opt) => opt.dataset.kind);
    }

    function chooseKindForProfile(profile, preferredKind) {
        const available = getAvailableKinds(profile);
        if (available.includes(preferredKind)) return preferredKind;
        if (available.includes("wireguard")) return "wireguard";
        if (available.includes("amnezia")) return "amnezia";
        return available[0] || null;
    }

    function syncChoiceUi() {
        const availableProfiles = new Set(
            Array.from(selectEl.options).map((opt) => opt.dataset.profile)
        );
        profileButtons.forEach((btn) => {
            btn.disabled = !availableProfiles.has(btn.dataset.profile);
        });

        const availableKinds = new Set(getAvailableKinds(selectedProfile));
        kindButtons.forEach((btn) => {
            btn.disabled = !availableKinds.has(btn.dataset.kind);
        });

        setButtonState(profileButtons, selectedProfile, "profile");
        setButtonState(kindButtons, selectedKind, "kind");
    }

    function applySelection() {
        syncChoiceUi();
        const option = getMatchingOption(selectedProfile, selectedKind);
        if (!option) return;
        selectEl.value = option.value;
        wgDownloadState.index = parseInt(option.value, 10);
        updateWgConfigSummary(selectedProfile, selectedKind);
        if (wgDownloadState.qrOpen) {
            loadWgConfigQr(clientName, wgDownloadState.index).catch((e) => {
                console.error(e);
                setWgQrUiState("unavailable", e.message || "Не удалось сгенерировать QR-код.");
            });
        }
    }

    const listBase = absoluteApiUrl(api.clientConfig);
    if (!listBase) {
        showDownloadError("Не задан URL API конфигурации.");
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
        .then((data) => {
            if (!data.success) {
                throw new Error(data.message || "Не удалось получить список профилей.");
            }
            const items = data.items || [];
            if (items.length === 0) {
                throw new Error("Не найдено файлов .conf для этого клиента.");
            }

            const parsedItems = items.map((it) => ({
                ...it,
                ...parseWgProfile(it.label),
            }));

            wgDownloadState = {
                clientName,
                items: parsedItems,
                index: parsedItems[0].index,
                qrOpen: false,
            };

            const knownItems = parsedItems.filter(
                (it) =>
                    (it.group === "antizapret" || it.group === "vpn") &&
                    (it.kind === "wireguard" || it.kind === "amnezia")
            );

            if (knownItems.length !== parsedItems.length) {
                selectEl.classList.remove("d-none");
                selectEl.removeAttribute("aria-hidden");
                selectEl.removeAttribute("tabindex");
                selectEl.classList.add("form-select", "mb-3");
                if (profileSelectLabel) profileSelectLabel.classList.remove("d-none");
                if (profileWrap) profileWrap.classList.add("d-none");
                if (kindWrap) kindWrap.classList.add("d-none");

                parsedItems.forEach((it) => {
                    const opt = document.createElement("option");
                    opt.value = String(it.index);
                    opt.textContent = it.label || `Профиль ${it.index}`;
                    selectEl.appendChild(opt);
                });

                function syncFallbackSummary() {
                    const item = parsedItems.find(
                        (it) => String(it.index) === String(selectEl.value)
                    );
                    const opt = selectEl.options[selectEl.selectedIndex];
                    updateWgConfigSummary(
                        item && item.group,
                        item && item.kind,
                        opt ? opt.textContent : ""
                    );
                }

                selectEl.onchange = () => {
                    wgDownloadState.index = parseInt(selectEl.value, 10);
                    syncFallbackSummary();
                    if (wgDownloadState.qrOpen) {
                        loadWgConfigQr(clientName, wgDownloadState.index).catch((e) => {
                            console.error(e);
                            setWgQrUiState(
                                "unavailable",
                                e.message || "Не удалось сгенерировать QR-код."
                            );
                        });
                    }
                };
                selectEl.value = String(items[0].index);
                syncFallbackSummary();
                loadingEl.classList.add("d-none");
                bodyEl.classList.remove("d-none");
                if (openQrOnReady) showWgQrPanel();
                return;
            }

            parsedItems.forEach((it) => {
                const opt = document.createElement("option");
                opt.value = String(it.index);
                opt.textContent = it.label || `Профиль ${it.index}`;
                opt.dataset.profile = it.group;
                opt.dataset.kind = it.kind;
                selectEl.appendChild(opt);
            });

            selectedProfile = parsedItems[0].group;
            selectedKind = parsedItems[0].kind;

            profileButtons.forEach((btn) => {
                btn.onclick = () => {
                    if (btn.disabled) return;
                    selectedProfile = btn.dataset.profile;
                    selectedKind = chooseKindForProfile(selectedProfile, selectedKind);
                    applySelection();
                };
            });

            kindButtons.forEach((btn) => {
                btn.onclick = () => {
                    if (btn.disabled) return;
                    selectedKind = btn.dataset.kind;
                    applySelection();
                };
            });

            loadingEl.classList.add("d-none");
            bodyEl.classList.remove("d-none");
            applySelection();
            if (openQrOnReady) showWgQrPanel();
        })
        .catch((e) => {
            console.error(e);
            showDownloadError(e.message || "Ошибка при запросе списка профилей.");
        });
}
