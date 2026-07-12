window.pendingOvpnBlock = null;
window.ovpnCertResultClient = null;

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
        if (!api || !api.kick || !api.block || !api.clientDelete) return;

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
                    } else if (action === "delete-client") {
                        url = api.clientDelete;
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
                } else if (action === "delete-client") {
                    titleEl.textContent = "Удаление клиента";
                    leadEl.innerHTML = `Удалить клиента ${nameHtml}?`;
                    hintEl.textContent =
                        "Клиент и файлы конфигурации OpenVPN будут удалены.";
                    confirmBtn.textContent = "Удалить";
                    confirmBtn.className = "btn btn-danger";
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

    function submitOpenvpnClientCert(clientName, days, submitBtn) {
        const api = window.ovpnApi;
        if (!api || !api.clientCert) {
            alert("API создания клиента недоступен.");
            return Promise.resolve();
        }

        const name = (clientName || "").trim();
        if (!/^[a-zA-Z0-9_-]{1,32}$/.test(name)) {
            alert("Некорректное имя. Используйте латиницу, цифры, _ и - (до 32 символов).");
            return Promise.resolve();
        }

        const daysNum = parseInt(days, 10);
        if (!Number.isFinite(daysNum) || daysNum < 1 || daysNum > 3650) {
            alert("Укажите срок от 1 до 3650 дней.");
            return Promise.resolve();
        }

        const originalText = submitBtn ? submitBtn.textContent : "";
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Выполняется…";
        }

        const formData = new FormData();
        formData.append("client_name", name);
        formData.append("days", String(daysNum));

        return fetch(api.clientCert, { method: "POST", body: formData })
            .then(async (response) => {
                const contentType = response.headers.get("content-type") || "";
                let data = {};
                if (contentType.includes("application/json")) {
                    data = await response.json();
                } else {
                    const text = await response.text();
                    throw new Error(text || `Ошибка сервера (${response.status})`);
                }
                return { ok: response.ok, data };
            })
            .then(({ ok, data }) => {
                if (!ok || !data.success) {
                    const msg = data.message || "Не удалось выполнить операцию.";
                    alert(msg.replace(/<[^>]+>/g, ""));
                    return;
                }
                showOvpnCertResult(data);
            })
            .catch((error) => {
                console.error(error);
                alert(error.message || "Ошибка при выполнении запроса.");
            })
            .finally(() => {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            });
    }

    function showOvpnCertResult(data) {
        const modalEl = document.getElementById("ovpnCertResultModal");
        const titleEl = document.getElementById("ovpnCertResultModalTitle");
        const messageEl = document.getElementById("ovpnCertResultMessage");
        const configHintEl = document.getElementById("ovpnCertResultConfigHint");
        const downloadBtn = document.getElementById("ovpnCertResultDownloadBtn");
        if (!modalEl || !titleEl || !messageEl) return;

        window.ovpnCertResultClient = data.client_name || null;
        titleEl.textContent = data.renewed ? "Сертификат продлён" : "Клиент создан";
        messageEl.innerHTML = data.message || "Операция выполнена.";

        const needNewConfig = Boolean(data.was_expired);
        const showDownload = Boolean(
            window.ovpnCertResultClient && (!data.renewed || data.was_expired)
        );
        if (configHintEl) {
            if (needNewConfig) {
                configHintEl.textContent =
                    "После продления сертификата старые файлы .ovpn не подходят — скачайте и раздайте клиенту новую конфигурацию.";
                configHintEl.classList.remove("d-none");
            } else {
                configHintEl.textContent = "";
                configHintEl.classList.add("d-none");
            }
        }
        if (downloadBtn) {
            downloadBtn.classList.toggle("d-none", !showDownload);
        }

        [
            document.getElementById("ovpnCreateClientModal"),
            document.getElementById("ovpnRenewClientModal"),
        ].forEach((el) => {
            if (!el) return;
            const inst = bootstrap.Modal.getInstance(el);
            if (inst) inst.hide();
        });

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    function setupOvpnCertModals() {
        const createBtn = document.getElementById("ovpnCreateClientBtn");
        const createModalEl = document.getElementById("ovpnCreateClientModal");
        const createNameEl = document.getElementById("ovpnCreateClientName");
        const createDaysEl = document.getElementById("ovpnCreateClientDays");
        const createSubmitEl = document.getElementById("ovpnCreateClientSubmit");

        if (createBtn && createModalEl) {
            createBtn.addEventListener("click", () => {
                if (createNameEl) createNameEl.value = "";
                if (createDaysEl) createDaysEl.value = "3650";
                bootstrap.Modal.getOrCreateInstance(createModalEl).show();
                if (createNameEl) setTimeout(() => createNameEl.focus(), 200);
            });
        }

        if (createSubmitEl) {
            createSubmitEl.addEventListener("click", () => {
                submitOpenvpnClientCert(
                    createNameEl ? createNameEl.value : "",
                    createDaysEl ? createDaysEl.value : "",
                    createSubmitEl
                );
            });
        }

        const renewModalEl = document.getElementById("ovpnRenewClientModal");
        const renewNameEl = document.getElementById("ovpnRenewClientName");
        const renewDaysEl = document.getElementById("ovpnRenewClientDays");
        const renewHintEl = document.getElementById("ovpnRenewClientHint");
        const renewSubmitEl = document.getElementById("ovpnRenewClientSubmit");

        document.querySelectorAll(".btn-renew-cert").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                const clientName = btn.dataset.client || "";
                const isExpired = btn.dataset.expired === "true";
                if (renewNameEl) renewNameEl.textContent = clientName;
                if (renewDaysEl) renewDaysEl.value = "3650";
                if (renewHintEl) {
                    renewHintEl.textContent = isExpired
                        ? "Срок сертификата истёк. После продления старые .ovpn не будут работать — нужна новая конфигурация."
                        : "Сертификат скоро истекает. Укажите новый срок действия.";
                }
                if (renewModalEl) {
                    bootstrap.Modal.getOrCreateInstance(renewModalEl).show();
                    if (renewDaysEl) setTimeout(() => renewDaysEl.focus(), 200);
                }
            });
        });

        if (renewSubmitEl) {
            renewSubmitEl.addEventListener("click", () => {
                submitOpenvpnClientCert(
                    renewNameEl ? renewNameEl.textContent.trim() : "",
                    renewDaysEl ? renewDaysEl.value : "",
                    renewSubmitEl
                );
            });
        }

        const resultReloadBtn = document.getElementById("ovpnCertResultReloadBtn");
        if (resultReloadBtn) {
            resultReloadBtn.addEventListener("click", () => {
                location.reload();
            });
        }

        const resultDownloadBtn = document.getElementById("ovpnCertResultDownloadBtn");
        if (resultDownloadBtn) {
            resultDownloadBtn.addEventListener("click", () => {
                const clientName = window.ovpnCertResultClient;
                if (!clientName) return;
                const resultModal = document.getElementById("ovpnCertResultModal");
                if (resultModal) {
                    const inst = bootstrap.Modal.getInstance(resultModal);
                    if (inst) inst.hide();
                }
                openOvpnDownloadModal(clientName);
            });
        }
    }

    setupOvpnCertModals();
});
