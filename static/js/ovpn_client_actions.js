window.pendingOvpnBlock = null;

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".ovpn-actions-menu-btn").forEach((el) => {
        if (typeof bootstrap !== "undefined" && bootstrap.Dropdown) {
            bootstrap.Dropdown.getOrCreateInstance(el, {
                popperConfig(defaultBsPopperConfig) {
                    return { ...defaultBsPopperConfig, strategy: "fixed" };
                },
            });
        }
    });

    function buildDownloadHref(api, clientName, index) {
        const u = new URL(api.clientConfigDownload, window.location.origin);
        u.searchParams.set("client_name", clientName);
        u.searchParams.set("index", String(index));
        return u.toString();
    }

    function openOvpnDownloadModal(clientName) {
        const api = window.ovpnApi;
        if (!api || !api.clientConfig || !api.clientConfigDownload) return;

        const modalEl = document.getElementById("ovpnConfigDownloadModal");
        const loadingEl = document.getElementById("ovpnConfigDownloadLoading");
        const bodyEl = document.getElementById("ovpnConfigDownloadBody");
        const selectEl = document.getElementById("ovpnConfigProfileSelect");
        const downloadEl = document.getElementById("ovpnConfigDownloadBtn");
        const profileSelectLabel = document.querySelector('label[for="ovpnConfigProfileSelect"]');

        if (!modalEl || !loadingEl || !bodyEl || !selectEl || !downloadEl) return;

        loadingEl.classList.remove("d-none");
        bodyEl.classList.add("d-none");
        selectEl.classList.add("d-none");
        selectEl.innerHTML = "";
        if (profileSelectLabel) profileSelectLabel.classList.add("d-none");

        const listUrl = new URL(api.clientConfig, window.location.origin);
        listUrl.searchParams.set("client_name", clientName);

        fetch(listUrl.toString())
            .then((r) => r.json())
            .then((data) => {
                loadingEl.classList.add("d-none");
                if (!data.success) {
                    alert(data.message || "Не удалось получить список профилей.");
                    return;
                }
                const items = data.items || [];
                if (items.length === 0) {
                    alert("Не найдено файлов .ovpn для этого клиента.");
                    return;
                }

                if (items.length === 1) {
                    window.location.href = buildDownloadHref(api, clientName, items[0].index);
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

                function syncDownload() {
                    const idx = parseInt(selectEl.value, 10);
                    downloadEl.href = buildDownloadHref(api, clientName, idx);
                }

                selectEl.onchange = syncDownload;
                syncDownload();

                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            })
            .catch((e) => {
                console.error(e);
                loadingEl.classList.add("d-none");
                alert("Ошибка при запросе списка профилей.");
            });
    }

    function setupOvpnActionButtons() {
        const api = window.ovpnApi;
        if (!api || !api.kick || !api.block) return;

        document.querySelectorAll(".btn-action[data-action]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const action = btn.dataset.action;
                const clientName = btn.dataset.client;
                const protocol = btn.dataset.protocol || "";
                const isOnline = btn.dataset.clientOnline === "true";

                if (action === "download-config") {
                    openOvpnDownloadModal(clientName);
                    return;
                }

                const doRequest = () => {
                    btn.disabled = true;
                    const labelEl = btn.querySelector(".ovpn-action-label");
                    const originalText = labelEl ? labelEl.textContent : btn.textContent;
                    if (labelEl) labelEl.textContent = "...";
                    else btn.textContent = "...";

                    const formData = new FormData();
                    formData.append("client_name", clientName);

                    let url;
                    if (action === "kick") {
                        url = api.kick;
                        formData.append("protocol", protocol);
                    } else {
                        url = api.block;
                        formData.append("blocked", action === "block" ? "true" : "false");
                    }

                    fetch(url, { method: "POST", body: formData })
                        .then((response) => response.json())
                        .then((data) => {
                            if (data.success) {
                                location.reload();
                            } else {
                                alert("Ошибка: " + (data.message || "Неизвестная ошибка"));
                                if (labelEl) labelEl.textContent = originalText;
                                else btn.textContent = originalText;
                                btn.disabled = false;
                            }
                        })
                        .catch((error) => {
                            console.error("Error:", error);
                            alert("Ошибка при выполнении запроса");
                            if (labelEl) labelEl.textContent = originalText;
                            else btn.textContent = originalText;
                            btn.disabled = false;
                        });
                };

                const modalEl = document.getElementById("confirmOvpnBlockModal");
                const titleEl = document.getElementById("confirmOvpnModalTitle");
                const leadEl = document.getElementById("confirmOvpnModalLead");
                const hintEl = document.getElementById("confirmOvpnModalHint");
                const confirmBtn = document.getElementById("confirmOvpnBlockBtn");

                if (!modalEl || !titleEl || !leadEl || !hintEl || !confirmBtn) {
                    doRequest();
                    return;
                }

                const esc = (s) =>
                    String(s)
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/"/g, "&quot;");
                const nameHtml = `<strong>${esc(clientName)}</strong>`;

                if (action === "kick") {
                    titleEl.textContent = "Отключение от сети";
                    leadEl.innerHTML = `Клиент ${nameHtml} будет отключён от сети и заблокирован в конфигурации.`;
                    hintEl.textContent =
                        "Сессия будет сброшена, имя клиента попадёт в список блокировок (banned_clients).";
                    confirmBtn.textContent = "Отключить";
                    confirmBtn.className = "btn btn-danger";
                } else if (action === "block") {
                    titleEl.textContent = "Блокировка в конфигурации";
                    leadEl.innerHTML = `Заблокировать клиента ${nameHtml} в конфигурации?`;
                    hintEl.textContent =
                        "Клиент не сможет подключаться к OpenVPN, пока блокировка не будет снята.";
                    confirmBtn.textContent = "Заблокировать";
                    confirmBtn.className = "btn btn-danger";
                } else if (action === "unblock") {
                    titleEl.textContent = "Разблокировка";
                    if (isOnline) {
                        leadEl.innerHTML = `Клиент ${nameHtml} сейчас в сети. Он будет отключён от сети; в конфигурации будет снят запрет (разблокировка).`;
                        hintEl.textContent =
                            "Активная сессия завершится; после переподключения клиент сможет работать без блокировки в конфигурации.";
                    } else {
                        leadEl.innerHTML = `Снять запрет на подключение для ${nameHtml}?`;
                        hintEl.textContent = "";
                    }
                    confirmBtn.textContent = "Разблокировать";
                    confirmBtn.className = "btn btn-primary";
                }

                window.pendingOvpnBlock = doRequest;
                bootstrap.Modal.getOrCreateInstance(modalEl).show();
            });
        });
    }

    setupOvpnActionButtons();

    const confirmBlockBtn = document.getElementById("confirmOvpnBlockBtn");
    const confirmBlockModalEl = document.getElementById("confirmOvpnBlockModal");

    if (confirmBlockBtn && confirmBlockModalEl) {
        confirmBlockBtn.addEventListener("click", () => {
            const modal = bootstrap.Modal.getInstance(confirmBlockModalEl);
            if (modal) {
                modal.hide();
            }
            if (window.pendingOvpnBlock) {
                window.pendingOvpnBlock();
                window.pendingOvpnBlock = null;
            }
        });

        confirmBlockModalEl.addEventListener("hidden.bs.modal", () => {
            window.pendingOvpnBlock = null;
        });
    }
});
