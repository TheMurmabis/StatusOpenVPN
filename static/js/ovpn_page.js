document.addEventListener("DOMContentLoaded", () => {
    const showIpCheckbox = document.getElementById("show-ip-checkbox");
    const savedShowIpState = localStorage.getItem("showOvpnIp") === "true";

    function applyIpVisibility(showFull) {
        document.querySelectorAll(".real-ip-cell").forEach((cell) => {
            const full = cell.getAttribute("data-real-ip");
            const masked = cell.getAttribute("data-masked-ip");
            if (full && masked) {
                cell.textContent = showFull ? full.split(":")[0] : masked;
            }
        });
    }

    if (showIpCheckbox) {
        showIpCheckbox.checked = savedShowIpState;
        applyIpVisibility(savedShowIpState);
        showIpCheckbox.addEventListener("change", () => {
            applyIpVisibility(showIpCheckbox.checked);
            localStorage.setItem("showOvpnIp", String(showIpCheckbox.checked));
        });
    }

    const tbody = document.getElementById("ovpn-clients-tbody");
    const autoRefreshCheckbox = document.getElementById("ovpn-auto-refresh-toggle");
    const countdownEl = document.getElementById("ovpn-refresh-countdown");
    const REFRESH_INTERVAL_SECONDS = 30;
    const base = typeof window.basePath === "string" ? window.basePath : "";

    function getOvpnClientsApiUrl() {
        const q = new URLSearchParams(window.location.search);
        const sort = q.get("sort") || "client";
        const order = q.get("order") || "asc";
        return `${base}/api/ovpn/clients?sort=${encodeURIComponent(sort)}&order=${encodeURIComponent(order)}`;
    }

    function ovpnClientSignature(c) {
        return JSON.stringify({
            blocked: c.blocked,
            display_name: c.display_name || c.name,
            real_ip: c.real_ip,
            local_ip: c.local_ip,
            received: c.received,
            sent: c.sent,
            download_speed: c.download_speed,
            upload_speed: c.upload_speed,
            connected_since: c.connected_since,
            duration: c.duration,
            protocol: c.protocol,
        });
    }

    function protocolCellHtml(client) {
        if (!client.real_ip || client.real_ip === "-" || !client.real_ip.includes(":")) {
            return client.protocol;
        }
        const port = client.real_ip.split(":")[1];
        if (port) {
            return `${client.protocol} (${port})`;
        }
        return client.protocol;
    }

    function buildOvpnSessionRow(client) {
        const tr = document.createElement("tr");
        tr.className =
            "text-center log-row ovpn-session-row" +
            (client.blocked ? " client-blocked" : "");
        tr.dataset.rowKey = client.row_key;
        tr.dataset.clientName = client.name;
        tr.dataset.online = "true";
        tr.dataset.blocked = client.blocked ? "true" : "false";
        tr.dataset.protocol = client.protocol;

        const display = client.display_name || client.name;
        const tdClient = document.createElement("td");
        tdClient.className = "text-center vpn-table-client";
        tdClient.textContent = display;
        tr.appendChild(tdClient);

        const tdReal = document.createElement("td");
        tdReal.className = "text-center";
        if (client.real_ip && client.real_ip !== "-") {
            const ipPart = client.real_ip.split(":")[0];
            const segs = ipPart.split(".");
            const masked =
                segs.length >= 4
                    ? `${parseInt(segs[0], 10)}.***.***.${parseInt(segs[segs.length - 1], 10)}`
                    : "-";
            tdReal.classList.add("real-ip-cell");
            tdReal.dataset.realIp = client.real_ip;
            tdReal.dataset.maskedIp = masked;
            tdReal.textContent = masked;
        } else {
            tdReal.textContent = "-";
        }
        tr.appendChild(tdReal);

        const tdLocal = document.createElement("td");
        tdLocal.className = "text-center";
        tdLocal.textContent = client.local_ip;
        tr.appendChild(tdLocal);

        const tdRec = document.createElement("td");
        tdRec.className = "text-center";
        tdRec.appendChild(document.createTextNode(client.received));
        if (client.download_speed && client.download_speed !== "-") {
            const sp = document.createElement("span");
            sp.className = "ovpn-speed";
            sp.textContent = `↓ ${client.download_speed}`;
            tdRec.appendChild(sp);
        }
        tr.appendChild(tdRec);

        const tdSent = document.createElement("td");
        tdSent.className = "text-center";
        tdSent.appendChild(document.createTextNode(client.sent));
        if (client.upload_speed && client.upload_speed !== "-") {
            const sp = document.createElement("span");
            sp.className = "ovpn-speed";
            sp.textContent = `↑ ${client.upload_speed}`;
            tdSent.appendChild(sp);
        }
        tr.appendChild(tdSent);

        const tdConn = document.createElement("td");
        tdConn.className = "text-center";
        if (client.connected_since && client.connected_since !== "-") {
            tdConn.classList.add("connection-time");
            tdConn.dataset.utc = client.connected_since;
            tdConn.textContent = client.connected_since;
        } else {
            tdConn.textContent = "-";
        }
        tr.appendChild(tdConn);

        const tdDur = document.createElement("td");
        tdDur.className = "text-center";
        tdDur.textContent = client.duration;
        tr.appendChild(tdDur);

        const tdProto = document.createElement("td");
        tdProto.className = "text-center";
        tdProto.textContent = protocolCellHtml(client);
        tr.appendChild(tdProto);

        tr.dataset.ovpnSig = ovpnClientSignature(client);
        return tr;
    }

    function patchOvpnSessionRow(tr, client) {
        tr.className =
            "text-center log-row ovpn-session-row" +
            (client.blocked ? " client-blocked" : "");
        tr.dataset.blocked = client.blocked ? "true" : "false";

        const cells = tr.children;
        const display = client.display_name || client.name;
        cells[0].textContent = display;

        const tdReal = cells[1];
        tdReal.className = "text-center";
        tdReal.removeAttribute("data-real-ip");
        tdReal.removeAttribute("data-masked-ip");
        if (client.real_ip && client.real_ip !== "-") {
            const ipPart = client.real_ip.split(":")[0];
            const segs = ipPart.split(".");
            const masked =
                segs.length >= 4
                    ? `${parseInt(segs[0], 10)}.***.***.${parseInt(segs[segs.length - 1], 10)}`
                    : "-";
            tdReal.classList.add("real-ip-cell");
            tdReal.dataset.realIp = client.real_ip;
            tdReal.dataset.maskedIp = masked;
            if (showIpCheckbox && showIpCheckbox.checked) {
                tdReal.textContent = client.real_ip.split(":")[0];
            } else {
                tdReal.textContent = masked;
            }
        } else {
            tdReal.textContent = "-";
        }

        cells[2].textContent = client.local_ip;

        const tdRec = cells[3];
        tdRec.textContent = "";
        tdRec.appendChild(document.createTextNode(client.received));
        if (client.download_speed && client.download_speed !== "-") {
            const sp = document.createElement("span");
            sp.className = "ovpn-speed";
            sp.textContent = `↓ ${client.download_speed}`;
            tdRec.appendChild(sp);
        }

        const tdSent = cells[4];
        tdSent.textContent = "";
        tdSent.appendChild(document.createTextNode(client.sent));
        if (client.upload_speed && client.upload_speed !== "-") {
            const sp = document.createElement("span");
            sp.className = "ovpn-speed";
            sp.textContent = `↑ ${client.upload_speed}`;
            tdSent.appendChild(sp);
        }

        const tdConn = cells[5];
        tdConn.className = "text-center";
        tdConn.removeAttribute("data-utc");
        if (client.connected_since && client.connected_since !== "-") {
            tdConn.classList.add("connection-time");
            tdConn.dataset.utc = client.connected_since;
            tdConn.textContent = client.connected_since;
        } else {
            tdConn.textContent = "-";
        }

        cells[6].textContent = client.duration;
        cells[7].textContent = protocolCellHtml(client);

        tr.dataset.ovpnSig = ovpnClientSignature(client);
    }

    function convertConnectionTimesIn(root) {
        (root || document).querySelectorAll(".connection-time").forEach((cell) => {
            const utcDateStr = cell.getAttribute("data-utc");
            if (utcDateStr) {
                const utcDate = new Date(utcDateStr);
                if (!Number.isNaN(utcDate.getTime())) {
                    cell.textContent = utcDate.toLocaleString();
                }
            }
        });
    }

    function applyOvpnSnapshot(data) {
        if (!tbody || !data || !data.ok) return;

        const online = data.online || [];
        const payloadKey = JSON.stringify(
            online.map((c) => [c.row_key, ovpnClientSignature(c)])
        );
        if (window.__ovpnLastPayloadKey === payloadKey) {
            return;
        }
        window.__ovpnLastPayloadKey = payloadKey;
        const footerRow = tbody.querySelector(".vpn-tfoot-totals");
        let emptyRow = tbody.querySelector(".ovpn-empty-row");

        const onlineEl = document.getElementById("ovpn-footer-online");
        const recvEl = document.getElementById("ovpn-footer-received");
        const sentEl = document.getElementById("ovpn-footer-sent");
        if (onlineEl) {
            onlineEl.textContent = `Онлайн: ${data.total_clients_str}`;
        }
        if (recvEl) recvEl.textContent = data.total_received;
        if (sentEl) sentEl.textContent = data.total_sent;

        if (online.length === 0) {
            tbody.querySelectorAll(".ovpn-session-row").forEach((tr) => tr.remove());
            if (!emptyRow) {
                emptyRow = document.createElement("tr");
                emptyRow.className = "ovpn-empty-row";
                const td = document.createElement("td");
                td.colSpan = 8;
                td.className = "text-center text-muted py-4";
                td.textContent = "Нет клиентов в сети";
                emptyRow.appendChild(td);
                tbody.insertBefore(emptyRow, footerRow);
            }
            emptyRow.style.display = "";
            return;
        }

        if (emptyRow) {
            emptyRow.style.display = "none";
        }

        const existing = new Map();
        tbody.querySelectorAll(".ovpn-session-row").forEach((tr) => {
            existing.set(tr.dataset.rowKey, tr);
        });
        const newKeys = new Set(online.map((c) => c.row_key));

        for (const key of existing.keys()) {
            if (!newKeys.has(key)) {
                existing.get(key).remove();
                existing.delete(key);
            }
        }

        let anchor = footerRow;
        for (let i = online.length - 1; i >= 0; i -= 1) {
            const client = online[i];
            const sig = ovpnClientSignature(client);
            let tr = existing.get(client.row_key);
            if (!tr) {
                tr = buildOvpnSessionRow(client);
                tbody.insertBefore(tr, anchor);
                existing.set(client.row_key, tr);
            } else {
                if (tr.dataset.ovpnSig !== sig) {
                    patchOvpnSessionRow(tr, client);
                }
                tbody.insertBefore(tr, anchor);
            }
            tr.dataset.ovpnSig = sig;
            anchor = tr;
        }

        if (showIpCheckbox) {
            applyIpVisibility(showIpCheckbox.checked);
        }
        convertConnectionTimesIn(tbody);
    }

    function fetchOvpnPartialUpdate() {
        if (!tbody) {
            return Promise.resolve();
        }
        return fetch(getOvpnClientsApiUrl(), { credentials: "same-origin" })
            .then((resp) => {
                if (!resp.ok) throw new Error(String(resp.status));
                return resp.json();
            })
            .then((data) => {
                applyOvpnSnapshot(data);
            })
            .catch(() => {});
    }

    function updateCountdown(secondsLeft) {
        if (!countdownEl) return;
        if (secondsLeft <= 0) {
            countdownEl.textContent = "0 с";
        } else {
            countdownEl.textContent = `${secondsLeft} с`;
        }
    }

    function startOvpnAutoRefresh() {
        if (!autoRefreshCheckbox) return;

        const nextTsMs = Date.now() + REFRESH_INTERVAL_SECONDS * 1000;
        localStorage.setItem("ovpnNextRefreshTs", String(nextTsMs));

        function tick() {
            if (!autoRefreshCheckbox.checked) {
                updateCountdown(0);
                return;
            }

            const stored = localStorage.getItem("ovpnNextRefreshTs");
            const nowMs = Date.now();
            let targetMs = stored ? parseInt(stored, 10) : NaN;

            if (!targetMs || Number.isNaN(targetMs)) {
                targetMs = nowMs + REFRESH_INTERVAL_SECONDS * 1000;
                localStorage.setItem("ovpnNextRefreshTs", String(targetMs));
            }

            let diffSec = Math.round((targetMs - nowMs) / 1000);

            if (diffSec <= 0) {
                const newNext = nowMs + REFRESH_INTERVAL_SECONDS * 1000;
                localStorage.setItem("ovpnNextRefreshTs", String(newNext));
                updateCountdown(0);
                fetchOvpnPartialUpdate().finally(() => {
                    setTimeout(tick, 1000);
                });
                return;
            }

            updateCountdown(diffSec);
            setTimeout(tick, 1000);
        }

        tick();
    }

    function stopOvpnAutoRefresh() {
        updateCountdown(0);
    }

    if (autoRefreshCheckbox) {
        const savedAutoRefresh = localStorage.getItem("ovpnAutoRefresh") === "true";
        if (savedAutoRefresh) {
            autoRefreshCheckbox.checked = true;
            startOvpnAutoRefresh();
        } else {
            stopOvpnAutoRefresh();
        }

        autoRefreshCheckbox.addEventListener("change", () => {
            const enabled = autoRefreshCheckbox.checked;
            localStorage.setItem("ovpnAutoRefresh", String(enabled));
            if (enabled) {
                startOvpnAutoRefresh();
            } else {
                stopOvpnAutoRefresh();
            }
        });
    }

    convertConnectionTimesIn(document);
});
