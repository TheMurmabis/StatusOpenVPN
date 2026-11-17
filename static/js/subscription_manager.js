document.addEventListener("DOMContentLoaded", () => {
    const api = window.subscriptionManagerApi || {};
    const modalEl = document.getElementById("subscriptionManagerModal");
    if (!modalEl || !api.settings || !api.create || !api.revoke) return;

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const loading = document.getElementById("subscriptionManagerLoading");
    const alertEl = document.getElementById("subscriptionManagerAlert");
    const servicesWarning = document.getElementById("subscriptionManagerServicesWarning");
    const form = document.getElementById("subscriptionManagerForm");
    const clientEl = document.getElementById("subscriptionManagerClient");
    const urlInput = document.getElementById("subscriptionManagerUrl");
    const mode = document.getElementById("subscriptionManagerMode");
    const modeHint = document.getElementById("subscriptionManagerModeHint");
    const openvpn = document.getElementById("subscriptionManagerOpenvpn");
    const wireguard = document.getElementById("subscriptionManagerWireguard");
    const familyTabs = document.getElementById("subscriptionFamilyTabs");
    const profileGrid = document.getElementById("subscriptionProfileGrid");
    const familyTabButtons = familyTabs
        ? Array.from(familyTabs.querySelectorAll("[data-family]"))
        : [];
    let mobileFamily = "openvpn";
    const protocolsWarning = document.getElementById("subscriptionManagerProtocolsWarning");
    const saveBtn = document.getElementById("subscriptionManagerSave");
    const copyBtn = document.getElementById("subscriptionManagerCopy");
    const copyIcon = copyBtn.querySelector("i");
    const rotateBtn = document.getElementById("subscriptionManagerRotate");
    const revokeBtn = document.getElementById("subscriptionManagerRevoke");
    const urlHint = document.getElementById("subscriptionManagerUrlHint");
    const rotateHint = document.getElementById("subscriptionManagerRotateHint");
    const protocolInputs = Array.from(form.querySelectorAll(".subscription-manager-protocol"));
    const actionButtons = [saveBtn, copyBtn, rotateBtn, revokeBtn];
    let currentClient = "";
    let currentFamily = "all";
    let lifetimeMinutes = 15;
    let isBusy = false;
    let copyResetTimer = 0;

    function setBusy(busy) {
        isBusy = busy;
        actionButtons.forEach((button) => { button.disabled = busy; });
        mode.disabled = busy;
        protocolInputs.forEach((input) => { input.disabled = busy; });
    }

    function showAlert(message, kind = "success") {
        alertEl.textContent = message;
        alertEl.className = `alert alert-${kind} py-2 px-3 small`;
    }

    function clearAlert() {
        alertEl.textContent = "";
        alertEl.className = "alert py-2 px-3 small d-none";
    }

    function renderServiceWarnings(warnings) {
        if (!servicesWarning) return;
        const items = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
        servicesWarning.replaceChildren();
        servicesWarning.classList.toggle("d-none", items.length === 0);
        if (!items.length) return;
        const title = document.createElement("div");
        title.className = "fw-semibold mb-1";
        title.textContent = "Некоторые конфигурации могут не работать";
        servicesWarning.appendChild(title);
        const list = document.createElement("ul");
        list.className = "mb-0 ps-3";
        items.forEach((message) => {
            const item = document.createElement("li");
            item.textContent = message;
            list.appendChild(item);
        });
        servicesWarning.appendChild(list);
    }

    async function responseJson(response) {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.message || "Не удалось выполнить действие.");
        }
        return data;
    }

    function copyText(value) {
        return new Promise((resolve) => {
            const area = document.createElement("textarea");
            area.value = value;
            area.setAttribute("readonly", "");
            area.setAttribute("aria-hidden", "true");
            area.tabIndex = -1;
            area.style.position = "fixed";
            area.style.top = "0";
            area.style.left = "0";
            area.style.width = "1px";
            area.style.height = "1px";
            area.style.opacity = "0";
            area.style.pointerEvents = "none";
            modalEl.appendChild(area);

            let copied = false;
            const onCopy = (event) => {
                if (!event.clipboardData) return;
                event.clipboardData.setData("text/plain", value);
                event.preventDefault();
                copied = true;
            };
            document.addEventListener("copy", onCopy, true);
            area.focus({ preventScroll: true });
            area.select();
            area.setSelectionRange(0, value.length);
            const selected = area.value.slice(area.selectionStart, area.selectionEnd);
            let commandOk = false;
            try { commandOk = document.execCommand("copy"); } catch (_) {}
            document.removeEventListener("copy", onCopy, true);
            window.setTimeout(() => area.remove(), 150);
            if (copied || (commandOk && selected === value)) {
                resolve(true);
                return;
            }
            if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(value).then(() => {
                    if (!navigator.clipboard.readText) {
                        resolve(false);
                        return;
                    }
                    navigator.clipboard.readText().then(
                        (read) => resolve(read === value),
                        () => resolve(false)
                    );
                }, () => resolve(false));
                return;
            }
            resolve(false);
        });
    }

    function resetCopyButton() {
        window.clearTimeout(copyResetTimer);
        copyIcon.className = "bi bi-copy";
        copyBtn.classList.remove("is-copied");
        copyBtn.title = "Копировать";
        copyBtn.setAttribute("aria-label", "Копировать");
    }

    function setUrl(value) {
        urlInput.value = value || "";
        const hasUrl = Boolean(urlInput.value);
        resetCopyButton();
        urlHint.classList.toggle("d-none", hasUrl);
        if (!hasUrl) urlHint.textContent = "Ссылка будет создана после сохранения.";
        copyBtn.classList.toggle("d-none", !hasUrl);
        rotateBtn.classList.toggle("d-none", !hasUrl);
        revokeBtn.classList.toggle("d-none", !hasUrl);
        rotateHint.classList.toggle("d-none", !hasUrl);
    }

    function updateClientTableStatus({ enabled = true, url = "", temporary = true }) {
        const cells = Array.from(document.querySelectorAll("[data-public-link-status]"));
        const cell = cells.find((item) => item.dataset.publicLinkStatus === currentClient);
        if (!cell) return;
        const row = cell.closest("tr");
        if (row) row.classList.toggle("public-link-client--disabled", !enabled);
        cell.replaceChildren();
        if (!enabled) {
            cell.textContent = "Отключено";
            return;
        }
        if (url) {
            cell.textContent = temporary ? "Временная" : "Постоянная";
            return;
        }
        const empty = document.createElement("span");
        empty.className = "text-muted";
        empty.textContent = "—";
        cell.appendChild(empty);
    }

    async function copyCurrentUrl() {
        if (isBusy || !urlInput.value) return;
        const copied = await copyText(urlInput.value);
        if (copied) {
            copyIcon.className = "bi bi-check2";
            copyBtn.classList.add("is-copied");
            copyBtn.title = "Скопировано";
            copyBtn.setAttribute("aria-label", "Скопировано");
            window.clearTimeout(copyResetTimer);
            copyResetTimer = window.setTimeout(resetCopyButton, 1600);
            showAlert("Ссылка скопирована.");
        } else {
            urlInput.focus();
            urlInput.select();
            showAlert("Скопируйте выделенную ссылку вручную.", "warning");
        }
    }

    function updateModeHint() {
        if (mode.value === "disabled") {
            modeHint.textContent = "Выдача ссылки будет отключена, действующая ссылка — отозвана.";
            return;
        }
        modeHint.textContent = mode.value === "true"
            ? `Ссылка действует ${lifetimeMinutes} мин. после первого открытия.`
            : "Ссылка действует до обновления или отзыва.";
    }

    function hasSelectedProtocols() {
        return protocolInputs.some((input) => {
            const group = input.closest("fieldset");
            return input.checked && group && !group.classList.contains("d-none");
        });
    }

    function setMobileFamily(family) {
        mobileFamily = family === "wireguard" ? "wireguard" : "openvpn";
        openvpn.classList.toggle("is-mobile-active", mobileFamily === "openvpn");
        wireguard.classList.toggle("is-mobile-active", mobileFamily === "wireguard");
        familyTabButtons.forEach((button) => {
            const active = button.dataset.family === mobileFamily;
            button.classList.toggle("active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });
    }

    function updateFamilyTabs(showOpenvpn, showWireguard) {
        const both = showOpenvpn && showWireguard;
        if (familyTabs) familyTabs.classList.toggle("d-none", !both);
        if (profileGrid) profileGrid.classList.toggle("has-family-tabs", both);
        if (!both) {
            openvpn.classList.add("is-mobile-active");
            wireguard.classList.add("is-mobile-active");
            return;
        }
        if (mobileFamily === "wireguard" && showWireguard) {
            setMobileFamily("wireguard");
            return;
        }
        setMobileFamily("openvpn");
    }

    function updateProtocolsWarning() {
        protocolsWarning.classList.toggle("d-none", hasSelectedProtocols());
    }

    function confirmDisabledProtocols() {
        if (hasSelectedProtocols()) return true;
        const familyName = currentFamily === "wireguard"
            ? "WireGuard"
            : (currentFamily === "openvpn" ? "OpenVPN" : "");
        if (!familyName) {
            return window.confirm(
                "Ни один конфиг не выбран. После сохранения выдача ссылки будет отключена, а действующая ссылка отозвана. Продолжить?"
            );
        }
        return window.confirm(
            `Ни один конфиг ${familyName} не выбран. Если других выбранных конфигураций нет, выдача ссылки будет отключена. Продолжить?`
        );
    }

    async function loadSettings() {
        setUrl("");
        loading.classList.remove("d-none");
        form.classList.add("d-none");
        saveBtn.classList.add("d-none");
        clearAlert();
        renderServiceWarnings([]);
        const url = new URL(api.settings, window.location.origin);
        url.searchParams.set("client_name", currentClient);
        if (currentFamily === "openvpn" || currentFamily === "wireguard") {
            url.searchParams.set("family", currentFamily);
        }
        try {
            const data = await responseJson(await fetch(url));
            setUrl(data.url);
            if (data.enabled === false) {
                urlHint.textContent = "Выдача ссылки для клиента отключена.";
            }
            lifetimeMinutes = Number(data.lifetime_minutes || 15);
            mode.value = data.enabled === false
                ? "disabled"
                : (data.temporary ? "true" : "false");
            const showOpenvpn = currentFamily === "openvpn" || (currentFamily === "all" && data.has_openvpn);
            const showWireguard = currentFamily === "wireguard" || (currentFamily === "all" && data.has_wireguard);
            openvpn.classList.toggle("d-none", !showOpenvpn);
            wireguard.classList.toggle("d-none", !showWireguard);
            updateFamilyTabs(showOpenvpn, showWireguard);
            protocolInputs.forEach((input) => {
                input.checked = Boolean((data.protocols || {})[input.dataset.key]);
            });
            renderServiceWarnings(data.service_warnings);
            updateModeHint();
            updateProtocolsWarning();
            form.classList.remove("d-none");
            saveBtn.classList.remove("d-none");
        } catch (error) {
            showAlert(error.message, "danger");
        } finally {
            loading.classList.add("d-none");
        }
    }

    async function saveSettings() {
        const body = new FormData();
        body.append("client_name", currentClient);
        if (currentFamily === "openvpn" || currentFamily === "wireguard") {
            body.append("family", currentFamily);
        }
        body.append("temporary", mode.value);
        protocolInputs.forEach((input) => {
            body.append(input.dataset.key, input.checked ? "true" : "false");
        });
        const data = await responseJson(await fetch(api.settings, { method: "POST", body }));
        setUrl(data.url);
        renderServiceWarnings(data.service_warnings);
        return data;
    }

    async function createLink(rotate = false) {
        const body = new FormData();
        body.append("client_name", currentClient);
        if (rotate) body.append("rotate", "true");
        return responseJson(await fetch(api.create, { method: "POST", body }));
    }

    async function saveSubscription() {
        if (!confirmDisabledProtocols()) return;
        setBusy(true);
        clearAlert();
        try {
            const settings = await saveSettings();
            if (settings.enabled === false) {
                setUrl("");
                mode.value = "disabled";
                updateModeHint();
                urlHint.textContent = "Выдача ссылки для клиента отключена.";
                updateClientTableStatus(settings);
                showAlert("Настройки сохранены. Выдача ссылки отключена.", "warning");
                return;
            }
            if (settings.url) {
                updateClientTableStatus(settings);
                showAlert("Настройки ссылки сохранены.");
                return;
            }
            const created = await createLink();
            setUrl(created.url);
            updateClientTableStatus({ ...created, enabled: true });
            showAlert("Настройки сохранены, ссылка создана.");
        } catch (error) {
            showAlert(error.message, "danger");
        } finally {
            setBusy(false);
        }
    }

    async function rotateLink() {
        if (!confirmDisabledProtocols()) return;
        setBusy(true);
        clearAlert();
        try {
            const settings = await saveSettings();
            if (settings.enabled === false) {
                setUrl("");
                mode.value = "disabled";
                updateModeHint();
                urlHint.textContent = "Выдача ссылки для клиента отключена.";
                updateClientTableStatus(settings);
                showAlert("Настройки сохранены. Выдача ссылки отключена.", "warning");
                return;
            }
            const data = await createLink(true);
            setUrl(data.url);
            updateClientTableStatus({ ...data, enabled: true });
            showAlert("Новая ссылка создана. Прежняя ссылка больше не работает.");
        } catch (error) {
            showAlert(error.message, "danger");
        } finally {
            setBusy(false);
        }
    }

    async function revokeLinks() {
        if (!window.confirm(`Отозвать все ссылки клиента ${currentClient}?`)) return;
        setBusy(true);
        clearAlert();
        try {
            const body = new FormData();
            body.append("client_name", currentClient);
            const data = await responseJson(await fetch(api.revoke, { method: "POST", body }));
            setUrl("");
            updateClientTableStatus({ enabled: true, url: "" });
            showAlert(data.message || "Ссылки клиента отозваны.");
        } catch (error) {
            showAlert(error.message, "danger");
        } finally {
            setBusy(false);
        }
    }

    mode.addEventListener("change", updateModeHint);
    copyBtn.addEventListener("click", copyCurrentUrl);
    protocolInputs.forEach((input) => {
        input.addEventListener("change", () => {
            updateProtocolsWarning();
            renderServiceWarnings([]);
        });
    });
    familyTabButtons.forEach((button) => {
        button.addEventListener("click", () => setMobileFamily(button.dataset.family));
    });
    saveBtn.addEventListener("click", saveSubscription);
    rotateBtn.addEventListener("click", () => {
        if (window.confirm("Создать новую ссылку? Прежняя ссылка перестанет работать.")) {
            rotateLink();
        }
    });
    revokeBtn.addEventListener("click", revokeLinks);

    window.SubscriptionManager = {
        open(clientName, family) {
            currentClient = String(clientName || "").trim();
            currentFamily = family === "wireguard" || family === "openvpn" ? family : "all";
            if (!currentClient) return;
            clientEl.textContent = currentClient;
            modal.show();
            loadSettings();
        },
    };
});
