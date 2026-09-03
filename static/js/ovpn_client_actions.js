window.pendingOvpnBlock = null;
window.ovpnCertResultClient = null;

document.addEventListener("DOMContentLoaded", () => {
    function buildDownloadHref(api, clientName, index) {
        const u = new URL(api.clientConfigDownload, window.location.origin);
        u.searchParams.set("client_name", clientName);
        u.searchParams.set("index", String(index));
        return u.toString();
    }

    function parseOvpnProfile(label) {
        const raw = String(label || "").trim();
        const lower = raw.toLowerCase();

        let group = "other";
        let groupLabel = "Другие";

        if (
            lower.startsWith("antizapret-") ||
            lower.includes("(antizapret")
        ) {
            group = "antizapret";
            groupLabel = "Antizapret";
        } else if (
            lower.startsWith("vpn-") ||
            lower.includes("(vpn")
        ) {
            group = "vpn";
            groupLabel = "VPN";
        }

        let protocol = "auto";
        let protocolLabel = "Автоматически";

        if (
            /-tcp\.ovpn/i.test(raw) ||
            /\((?:antizapret|vpn)-tcp\)/i.test(raw)
        ) {
            protocol = "tcp";
            protocolLabel = "TCP";
        } else if (
            /-udp\.ovpn/i.test(raw) ||
            /\((?:antizapret|vpn)-udp\)/i.test(raw)
        ) {
            protocol = "udp";
            protocolLabel = "UDP";
        }

        return {
            group,
            groupLabel,
            protocol,
            protocolLabel,
        };
    }

    function ovpnProfileTitle(profile) {
        if (profile === "antizapret") return "Antizapret";
        if (profile === "vpn") return "VPN";
        return "";
    }

    function ovpnProtocolTitle(protocol) {
        if (protocol === "tcp") return "TCP";
        if (protocol === "udp") return "UDP";
        if (protocol === "auto") return "Auto";
        return "";
    }

    function updateOvpnConfigSummary(profile, protocol, fallbackLabel) {
        const summaryEl = document.getElementById("ovpnConfigSelectionSummary");
        if (!summaryEl) return;
        const profileText = ovpnProfileTitle(profile);
        const protocolText = ovpnProtocolTitle(protocol);
        if (profileText && protocolText) {
            summaryEl.textContent = `${profileText} · ${protocolText}`;
        } else {
            summaryEl.textContent = fallbackLabel || "";
        }
    }

    function openOvpnDownloadModal(clientName) {
        const api = window.ovpnApi;
        if (!api || !api.clientConfig || !api.clientConfigDownload) return;

        const modalEl = document.getElementById("ovpnConfigDownloadModal");
        const loadingEl = document.getElementById("ovpnConfigDownloadLoading");
        const bodyEl = document.getElementById("ovpnConfigDownloadBody");
        const errorEl = document.getElementById("ovpnConfigDownloadError");
        const clientLabelEl = document.getElementById("ovpnConfigDownloadClient");
        const selectEl = document.getElementById("ovpnConfigProfileSelect");
        const downloadEl = document.getElementById("ovpnConfigDownloadBtn");
        const profileButtons = Array.from(
            document.querySelectorAll("#ovpnProfileType [data-profile]")
        );
        const protocolButtons = Array.from(
            document.querySelectorAll("#ovpnProtocolType [data-protocol]")
        );
        const profileTypeEl = document.getElementById("ovpnProfileType");
        const protocolTypeEl = document.getElementById("ovpnProtocolType");

        if (!modalEl || !loadingEl || !bodyEl || !selectEl || !downloadEl) return;

        function showDownloadError(message) {
            loadingEl.classList.add("d-none");
            bodyEl.classList.add("d-none");
            if (!errorEl) return;
            errorEl.textContent = message;
            errorEl.classList.remove("d-none");
        }

        if (clientLabelEl) clientLabelEl.textContent = clientName || "";
        if (errorEl) {
            errorEl.textContent = "";
            errorEl.classList.add("d-none");
        }

        let selectedProfile = null;
        let selectedProtocol = null;

        function setButtonState(buttons, activeValue, dataKey) {
            buttons.forEach((btn) => {
                const active = btn.dataset[dataKey] === activeValue;
                btn.classList.toggle("active", active);
                btn.setAttribute("aria-pressed", active ? "true" : "false");
            });
        }

        function getMatchingOption(profile, protocol) {
            return Array.from(selectEl.options).find(
                (opt) =>
                    opt.dataset.profile === profile &&
                    opt.dataset.protocol === protocol
            );
        }

        function getAvailableProtocols(profile) {
            return Array.from(selectEl.options)
                .filter((opt) => opt.dataset.profile === profile)
                .map((opt) => opt.dataset.protocol);
        }

        function chooseProtocolForProfile(profile, preferredProtocol) {
            const available = getAvailableProtocols(profile);

            if (available.includes(preferredProtocol)) return preferredProtocol;
            if (available.includes("auto")) return "auto";
            if (available.includes("tcp")) return "tcp";
            if (available.includes("udp")) return "udp";

            return available[0] || null;
        }

        function syncChoiceUi() {
            const availableProfiles = new Set(
                Array.from(selectEl.options).map((opt) => opt.dataset.profile)
            );

            profileButtons.forEach((btn) => {
                btn.disabled = !availableProfiles.has(btn.dataset.profile);
            });

            const availableProtocols = new Set(getAvailableProtocols(selectedProfile));
            protocolButtons.forEach((btn) => {
                btn.disabled = !availableProtocols.has(btn.dataset.protocol);
            });

            setButtonState(profileButtons, selectedProfile, "profile");
            setButtonState(protocolButtons, selectedProtocol, "protocol");
        }

        function syncDownload() {
            const option = getMatchingOption(selectedProfile, selectedProtocol);

            if (!option) {
                downloadEl.removeAttribute("href");
                downloadEl.classList.add("disabled");
                downloadEl.setAttribute("aria-disabled", "true");
                return;
            }

            selectEl.value = option.value;

            const idx = parseInt(option.value, 10);
            downloadEl.href = buildDownloadHref(api, clientName, idx);
            downloadEl.classList.remove("disabled");
            downloadEl.removeAttribute("aria-disabled");
        }

        function applySelection() {
            syncChoiceUi();
            syncDownload();
            updateOvpnConfigSummary(selectedProfile, selectedProtocol);
        }

        loadingEl.classList.remove("d-none");
        bodyEl.classList.add("d-none");
        selectEl.className = "d-none";
        selectEl.setAttribute("tabindex", "-1");
        selectEl.setAttribute("aria-hidden", "true");
        selectEl.onchange = null;
        selectEl.innerHTML = "";
        downloadEl.removeAttribute("href");
        downloadEl.classList.add("disabled");
        downloadEl.setAttribute("aria-disabled", "true");

        if (profileTypeEl) profileTypeEl.parentElement.classList.remove("d-none");
        if (protocolTypeEl) protocolTypeEl.parentElement.classList.remove("d-none");

        profileButtons.forEach((btn) => {
            btn.disabled = true;
            btn.classList.remove("active");
            btn.setAttribute("aria-pressed", "false");
        });

        protocolButtons.forEach((btn) => {
            btn.disabled = true;
            btn.classList.remove("active");
            btn.setAttribute("aria-pressed", "false");
        });

        updateOvpnConfigSummary("", "", "");

        bootstrap.Modal.getOrCreateInstance(modalEl).show();

        const listUrl = new URL(api.clientConfig, window.location.origin);
        listUrl.searchParams.set("client_name", clientName);

        fetch(listUrl.toString())
            .then((r) => r.json())
            .then((data) => {
                if (!data.success) {
                    showDownloadError(data.message || "Не удалось получить список профилей.");
                    return;
                }

                const items = data.items || [];

                if (items.length === 0) {
                    showDownloadError("Не найдено файлов .ovpn для этого клиента.");
                    return;
                }

                if (items.length === 1) {
                    const inst = bootstrap.Modal.getInstance(modalEl);
                    if (inst) inst.hide();
                    window.location.href = buildDownloadHref(api, clientName, items[0].index);
                    return;
                }

                loadingEl.classList.add("d-none");

                const parsedItems = items.map((it) => ({
                    ...it,
                    ...parseOvpnProfile(it.label),
                }));

                const knownItems = parsedItems.filter(
                    (it) => it.group === "antizapret" || it.group === "vpn"
                );

                if (knownItems.length !== parsedItems.length) {
                    selectEl.classList.remove("d-none");
                    selectEl.removeAttribute("aria-hidden");
                    selectEl.removeAttribute("tabindex");
                    selectEl.classList.add("form-select", "mb-3");

                    if (profileTypeEl) profileTypeEl.parentElement.classList.add("d-none");
                    if (protocolTypeEl) protocolTypeEl.parentElement.classList.add("d-none");

                    parsedItems.forEach((it) => {
                        const opt = document.createElement("option");
                        opt.value = String(it.index);
                        opt.textContent = it.label || `Профиль ${it.index}`;
                        selectEl.appendChild(opt);
                    });

                    function syncFallbackDownload() {
                        const idx = parseInt(selectEl.value, 10);
                        downloadEl.href = buildDownloadHref(api, clientName, idx);
                        downloadEl.classList.remove("disabled");
                        downloadEl.removeAttribute("aria-disabled");
                        const item = parsedItems.find((it) => Number(it.index) === idx);
                        const opt = selectEl.options[selectEl.selectedIndex];
                        updateOvpnConfigSummary(
                            item && item.group,
                            item && item.protocol,
                            opt ? opt.textContent : ""
                        );
                    }

                    selectEl.onchange = syncFallbackDownload;
                    selectEl.value = String(items[0].index);
                    syncFallbackDownload();
                    bodyEl.classList.remove("d-none");
                    return;
                }

                selectEl.className = "d-none";
                selectEl.setAttribute("tabindex", "-1");
                selectEl.setAttribute("aria-hidden", "true");
                selectEl.onchange = null;

                if (profileTypeEl) profileTypeEl.parentElement.classList.remove("d-none");
                if (protocolTypeEl) protocolTypeEl.parentElement.classList.remove("d-none");

                parsedItems.forEach((it) => {
                    const opt = document.createElement("option");
                    opt.value = String(it.index);
                    opt.textContent = it.label || `Профиль ${it.index}`;
                    opt.dataset.profile = it.group;
                    opt.dataset.protocol = it.protocol;
                    opt.dataset.originalLabel = it.label || "";
                    selectEl.appendChild(opt);
                });

                const initialItem = parsedItems[0];
                selectedProfile = initialItem.group;
                selectedProtocol = initialItem.protocol;

                profileButtons.forEach((btn) => {
                    btn.onclick = () => {
                        if (btn.disabled) return;

                        selectedProfile = btn.dataset.profile;
                        selectedProtocol = chooseProtocolForProfile(
                            selectedProfile,
                            selectedProtocol
                        );
                        applySelection();
                    };
                });

                protocolButtons.forEach((btn) => {
                    btn.onclick = () => {
                        if (btn.disabled) return;

                        selectedProtocol = btn.dataset.protocol;
                        applySelection();
                    };
                });

                bodyEl.classList.remove("d-none");
                applySelection();
            })
            .catch((e) => {
                console.error(e);
                showDownloadError("Ошибка при запросе списка профилей.");
            });
    }

    function setupOvpnActionButtons() {
        const api = window.ovpnApi;
        if (!api || !api.kick || !api.block || !api.clientDelete) return;

        document.querySelectorAll(".vpn-action-icon-btn[data-action]").forEach((btn) => {
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
                                btn.disabled = false;
                            }
                        })
                        .catch((error) => {
                            console.error("Error:", error);
                            alert("Ошибка при выполнении запроса");
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

    function formatDaysHint(days) {
        const n = parseInt(days, 10);
        if (!Number.isFinite(n) || n < 1) return "";
        if (n % 365 === 0) {
            const y = n / 365;
            const n10 = y % 10;
            const n100 = y % 100;
            if (n10 === 1 && n100 !== 11) return `${y} год`;
            if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return `${y} года`;
            return `${y} лет`;
        }
        return `${n} дн.`;
    }

    function setFieldInvalid(el, message) {
        if (!el) return;
        el.classList.add("is-invalid");
        const group = el.closest(".input-group");
        if (group) group.classList.add("is-invalid");
        const errorEl = document.getElementById(`${el.id}Error`);
        if (errorEl) {
            if (message) errorEl.textContent = message;
            errorEl.classList.add("d-block");
        }
    }

    function clearFieldInvalid(el) {
        if (!el) return;
        el.classList.remove("is-invalid");
        const group = el.closest(".input-group");
        if (group) group.classList.remove("is-invalid");
        const errorEl = document.getElementById(`${el.id}Error`);
        if (errorEl) errorEl.classList.remove("d-block");
    }

    function bindDaysField(daysEl, presetsRoot, hintEl) {
        if (!daysEl) return;
        const buttons = presetsRoot
            ? Array.from(presetsRoot.querySelectorAll("[data-days]"))
            : [];

        function sync() {
            const val = String(parseInt(daysEl.value, 10) || "");
            buttons.forEach((btn) => {
                btn.classList.toggle("active", btn.dataset.days === val);
            });
            if (hintEl) hintEl.textContent = formatDaysHint(daysEl.value);
            clearFieldInvalid(daysEl);
        }

        buttons.forEach((btn) => {
            btn.addEventListener("click", () => {
                daysEl.value = btn.dataset.days;
                sync();
            });
        });
        daysEl.addEventListener("input", sync);
        sync();
        return sync;
    }

    function submitOpenvpnClientCert(name, nameEl, daysEl, submitBtn) {
        const api = window.ovpnApi;
        if (!api || !api.clientCert) {
            alert("API создания клиента недоступен.");
            return Promise.resolve();
        }

        const resolvedName = (name || "").trim();
        clearFieldInvalid(nameEl);
        clearFieldInvalid(daysEl);

        if (!/^[a-zA-Z0-9_-]{1,32}$/.test(resolvedName)) {
            if (nameEl) {
                setFieldInvalid(
                    nameEl,
                    "Используйте латиницу, цифры, _ и - (до 32 символов)."
                );
                nameEl.focus();
            } else {
                alert("Некорректное имя. Используйте латиницу, цифры, _ и - (до 32 символов).");
            }
            return Promise.resolve();
        }

        const daysNum = parseInt(daysEl ? daysEl.value : "", 10);
        if (!Number.isFinite(daysNum) || daysNum < 1 || daysNum > 3650) {
            setFieldInvalid(daysEl, "Укажите срок от 1 до 3650 дней.");
            if (daysEl) daysEl.focus();
            return Promise.resolve();
        }

        const originalText = submitBtn ? submitBtn.textContent : "";
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Выполняется…";
        }

        const formData = new FormData();
        formData.append("client_name", resolvedName);
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
        const createFormEl = document.getElementById("ovpnCreateClientForm");
        const createNameEl = document.getElementById("ovpnCreateClientName");
        const createDaysEl = document.getElementById("ovpnCreateClientDays");
        const createSubmitEl = document.getElementById("ovpnCreateClientSubmit");
        const createDaysSync = bindDaysField(
            createDaysEl,
            createModalEl && createModalEl.querySelector(".ovpn-days-presets"),
            document.getElementById("ovpnCreateClientDaysHint")
        );

        if (createNameEl) {
            createNameEl.addEventListener("input", () => clearFieldInvalid(createNameEl));
        }

        if (createBtn && createModalEl) {
            createBtn.addEventListener("click", () => {
                if (createNameEl) createNameEl.value = "";
                if (createDaysEl) createDaysEl.value = "3650";
                clearFieldInvalid(createNameEl);
                clearFieldInvalid(createDaysEl);
                if (createDaysSync) createDaysSync();
                bootstrap.Modal.getOrCreateInstance(createModalEl).show();
                if (createNameEl) setTimeout(() => createNameEl.focus(), 200);
            });
        }

        if (createFormEl) {
            createFormEl.addEventListener("submit", (e) => {
                e.preventDefault();
                submitOpenvpnClientCert(
                    createNameEl ? createNameEl.value : "",
                    createNameEl,
                    createDaysEl,
                    createSubmitEl
                );
            });
        }

        const renewModalEl = document.getElementById("ovpnRenewClientModal");
        const renewFormEl = document.getElementById("ovpnRenewClientForm");
        const renewNameEl = document.getElementById("ovpnRenewClientName");
        const renewDaysEl = document.getElementById("ovpnRenewClientDays");
        const renewHintEl = document.getElementById("ovpnRenewClientHint");
        const renewSubmitEl = document.getElementById("ovpnRenewClientSubmit");
        const renewDaysSync = bindDaysField(
            renewDaysEl,
            renewModalEl && renewModalEl.querySelector(".ovpn-days-presets"),
            document.getElementById("ovpnRenewClientDaysHint")
        );

        document.querySelectorAll(".btn-renew-cert").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                const clientName = btn.dataset.client || "";
                const isExpired = btn.dataset.expired === "true";
                const renewState = btn.dataset.renewState || "";
                if (renewNameEl) renewNameEl.textContent = clientName;
                if (renewDaysEl) renewDaysEl.value = "3650";
                clearFieldInvalid(renewDaysEl);
                if (renewDaysSync) renewDaysSync();
                if (renewHintEl) {
                    if (isExpired) {
                        renewHintEl.textContent =
                            "Срок сертификата истёк. После продления старые .ovpn не будут работать — нужна новая конфигурация.";
                    } else if (renewState === "expiring") {
                        renewHintEl.textContent = "Сертификат скоро истекает. Укажите новый срок действия.";
                    } else {
                        renewHintEl.textContent = "Сертификат будет перевыпущен с указанным сроком действия.";
                    }
                }
                if (renewModalEl) {
                    bootstrap.Modal.getOrCreateInstance(renewModalEl).show();
                    if (renewDaysEl) setTimeout(() => renewDaysEl.focus(), 200);
                }
            });
        });

        if (renewFormEl) {
            renewFormEl.addEventListener("submit", (e) => {
                e.preventDefault();
                submitOpenvpnClientCert(
                    renewNameEl ? renewNameEl.textContent.trim() : "",
                    null,
                    renewDaysEl,
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

    const urlClient = (new URLSearchParams(window.location.search).get("client") || "").trim();
    if (urlClient) {
        const row = Array.from(document.querySelectorAll("tr[data-client-name]")).find(
            (el) => el.dataset.clientName === urlClient
        );
        if (row) {
            row.classList.add("vpn-client-row-flash");
            row.scrollIntoView({ behavior: "smooth", block: "center" });
            setTimeout(() => row.classList.remove("vpn-client-row-flash"), 2600);
        }
    }
});
