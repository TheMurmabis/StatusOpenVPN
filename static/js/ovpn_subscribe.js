document.addEventListener("DOMContentLoaded", () => {
    const state = window.ovpnSubscribe || {};
    const items = Array.isArray(state.items) ? state.items : [];
    const token = String(state.token || "");
    if (!token || items.length === 0) return;
    const temporary = Boolean(state.temporary);
    const expiresAt = Number(state.expiresAt || 0);

    const appButtons = Array.from(document.querySelectorAll("#subAppType [data-app]"));
    const profileButtons = Array.from(document.querySelectorAll("#subProfileType [data-profile]"));
    const protocolButtons = Array.from(document.querySelectorAll("#subProtocolType [data-protocol]"));
    const appDownload = document.getElementById("subAppDownload");
    const appHint = document.getElementById("subAppDownloadHint");
    const appStepTitle = document.getElementById("subAppStepTitle");
    const otherLinks = document.getElementById("subAppOtherLinks");
    const step2Desc = document.getElementById("subStep2Desc");
    const howTo = document.getElementById("subHowTo");
    const openBtn = document.getElementById("subOpenBtn");
    const downloadBtn = document.getElementById("subDownloadBtn");
    const qrBtn = document.getElementById("subQrBtn");
    const qrWrap = document.getElementById("subQrWrap");
    const qrImg = document.getElementById("subQrImg");
    const actionFeedback = document.getElementById("subActionFeedback");
    const expiryBadge = document.getElementById("subExpiryBadge");
    const expiryText = document.getElementById("subExpiryText");
    const expiryTimer = document.getElementById("subExpiryTimer");
    const qrFullscreenBtn = document.getElementById("subQrFullscreenBtn");
    const qrDownloadBtn = document.getElementById("subQrDownloadBtn");
    const qrDialog = document.getElementById("subQrDialog");
    const qrDialogImg = document.getElementById("subQrDialogImg");
    const qrDialogClose = document.getElementById("subQrDialogClose");
    const qrDialogDownload = document.getElementById("subQrDialogDownload");
    const profileWrap = document.getElementById("subProfileWrap");
    const protocolWrap = document.getElementById("subProtocolWrap");
    const protocolAdvanced = document.getElementById("subProtocolAdvanced");
    const familyTabs = document.getElementById("subFamilyTabs");
    const familyButtons = Array.from(document.querySelectorAll("#subFamilyTabs [data-family]"));

    const appMeta = {
        openvpn: {
            title: "OpenVPN Connect",
            shortName: "OpenVPN",
            how: [
                "Нажмите «Открыть в OpenVPN Connect»",
                "Разрешите браузеру открыть приложение",
                "Подтвердите импорт профиля",
            ],
            links: {
                android: { href: "https://play.google.com/store/apps/details?id=net.openvpn.openvpn", label: "Android" },
                ios: { href: "https://apps.apple.com/app/openvpn-connect/id590379981", label: "iOS" },
                windows: { href: "https://openvpn.net/downloads/openvpn-connect-v3-windows.msi", label: "Windows" },
                macos: { href: "https://openvpn.net/downloads/openvpn-connect-v3-macos.dmg", label: "macOS" },
                other: { href: "https://openvpn.net/client/", label: "Другие" },
            },
        },
        wireguard: {
            title: "WireGuard",
            shortName: "WireGuard",
            how: [
                "Скачайте конфигурацию или покажите QR-код",
                "Импортируйте файл либо отсканируйте QR-код в WireGuard",
                "Активируйте добавленный туннель",
            ],
            links: {
                android: { href: "https://play.google.com/store/apps/details?id=com.wireguard.android", label: "Android" },
                ios: { href: "https://apps.apple.com/app/wireguard/id1441195209", label: "iOS" },
                windows: { href: "https://www.wireguard.com/install/", label: "Windows" },
                macos: { href: "https://apps.apple.com/app/wireguard/id1451685025", label: "macOS" },
                other: { href: "https://www.wireguard.com/install/", label: "Другие" },
            },
        },
        amnezia: {
            title: "AmneziaWG",
            shortName: "AmneziaWG",
            how: [
                "Скачайте конфигурацию или покажите QR-код",
                "Импортируйте файл либо отсканируйте QR-код в AmneziaWG",
                "Активируйте добавленный туннель",
            ],
            links: {
                android: { href: "https://play.google.com/store/apps/details?id=org.amnezia.awg", label: "Android" },
                ios: { href: "https://apps.apple.com/app/amneziawg/id6478942365", label: "iOS" },
                windows: { href: "https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest", label: "Windows" },
                macos: { href: "https://apps.apple.com/app/amneziawg/id6478942365", label: "macOS" },
                other: { href: "https://play.google.com/store/apps/details?id=org.amnezia.awg", label: "Другие" },
            },
        },
    };

    function familyOfApp(app) {
        return app === "openvpn" ? "openvpn" : "wireguard";
    }

    function familyOf(item) {
        return item.family || "openvpn";
    }

    function appOf(item) {
        if (familyOf(item) === "openvpn") return "openvpn";
        return item.kind === "amnezia" ? "amnezia" : "wireguard";
    }

    function detectPlatform() {
        const ua = navigator.userAgent || "";
        if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
        if (/Android/i.test(ua)) return "android";
        if (/Windows/i.test(ua)) return "windows";
        if (/Mac OS X|Macintosh/i.test(ua)) return "macos";
        if (/Linux/i.test(ua)) return "linux";
        return "other";
    }

    function appsForFamily(family) {
        return Array.from(new Set(items.map(appOf).filter((app) => familyOfApp(app) === family)));
    }

    function itemsForApp(app) {
        return items.filter((item) => appOf(item) === app);
    }

    function profilesFor(app) {
        return itemsForApp(app).map((item) => item.profile);
    }

    function protocolsFor(app, profile) {
        return itemsForApp(app)
            .filter((item) => item.profile === profile)
            .map((item) => item.protocol);
    }

    function chooseValue(available, preferred, fallbacks) {
        if (available.includes(preferred)) return preferred;
        for (const value of fallbacks) {
            if (available.includes(value)) return value;
        }
        return available[0] || null;
    }

    function defaultAppForFamily(family) {
        const familyApps = appsForFamily(family);
        if (family === "openvpn") {
            return chooseValue(familyApps, "openvpn", familyApps);
        }
        return chooseValue(familyApps, "amnezia", ["wireguard"]);
    }

    function applyFamilyDefaults(family) {
        selectedFamily = family;
        selectedApp = defaultAppForFamily(family);
        selectedProfile = chooseValue(profilesFor(selectedApp), "antizapret", ["vpn"]);
        selectedProtocol = chooseValue(protocolsFor(selectedApp, selectedProfile), "auto", ["tcp", "udp"]);
    }

    function findItem() {
        return items.find((item) => {
            if (appOf(item) !== selectedApp) return false;
            if (item.profile !== selectedProfile) return false;
            if (selectedApp === "openvpn") return item.protocol === selectedProtocol;
            return true;
        });
    }

    function fileUrl(item) {
        const path = window.location.pathname.replace(/\/+$/, "");
        const ext = item.ext || (appOf(item) === "openvpn" ? "ovpn" : "conf");
        return `${window.location.origin}${path}/${item.slug}.${ext}`;
    }

    function qrUrl(item) {
        const path = window.location.pathname.replace(/\/+$/, "");
        return `${window.location.origin}${path}/${item.slug}.png`;
    }

    function setDisabled(el, disabled) {
        if (!el) return;
        el.classList.toggle("disabled", disabled);
        if (disabled) {
            el.setAttribute("aria-disabled", "true");
            el.setAttribute("tabindex", "-1");
            if (el.tagName === "A") el.removeAttribute("href");
        } else {
            el.removeAttribute("aria-disabled");
            el.removeAttribute("tabindex");
            if (el.tagName === "A" && el.dataset.href) {
                el.setAttribute("href", el.dataset.href);
            }
        }
        if (el.tagName === "BUTTON") el.disabled = disabled;
    }

    function setLink(el, href) {
        if (!el) return;
        if (href) el.dataset.href = href;
        else delete el.dataset.href;
        setDisabled(el, !href);
    }

    function setChoiceButtons(buttons, availableSet, dataKey, selectedValue) {
        buttons.forEach((btn) => {
            const available = availableSet.has(btn.dataset[dataKey]);
            btn.hidden = !available;
            btn.classList.toggle("d-none", !available);
            btn.disabled = !available;
            const active = available && btn.dataset[dataKey] === selectedValue;
            btn.classList.toggle("active", active);
            btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
    }

    function hideQr() {
        qrOpen = false;
        if (qrWrap) {
            qrWrap.hidden = true;
            qrWrap.classList.add("d-none");
        }
        if (qrImg) qrImg.removeAttribute("src");
        if (qrDialog && qrDialog.open) qrDialog.close();
        if (qrDialogImg) qrDialogImg.removeAttribute("src");
        if (qrBtn) qrBtn.textContent = "QR-код";
    }

    function hideActionFeedback() {
        if (!actionFeedback) return;
        actionFeedback.hidden = true;
        actionFeedback.textContent = "";
    }

    function showActionFeedback(message) {
        if (!actionFeedback) return;
        actionFeedback.textContent = message;
        actionFeedback.hidden = false;
    }

    function setQrSource(item) {
        const url = qrUrl(item);
        if (qrImg) qrImg.src = url;
        if (qrDialogImg) qrDialogImg.src = url;
        if (qrDownloadBtn) qrDownloadBtn.href = url;
        if (qrDialogDownload) qrDialogDownload.href = url;
    }

    function platformLabel(platform) {
        if (platform === "ios") return "iOS";
        if (platform === "android") return "Android";
        if (platform === "windows") return "Windows";
        if (platform === "macos") return "macOS";
        if (platform === "linux") return "Linux";
        return "";
    }

    function platformIcon(key) {
        if (key === "ios" || key === "macos") return "bi-apple";
        if (key === "android") return "bi-android2";
        if (key === "windows") return "bi-windows";
        if (key === "linux") return "bi-ubuntu";
        return "";
    }

    function platformIconHtml(key) {
        const name = platformIcon(key);
        if (!name) return "";
        return `<i class="bi ${name}" aria-hidden="true"></i>`;
    }

    let selectedApp = null;
    let selectedFamily = null;
    let selectedProfile = null;
    let selectedProtocol = null;
    let qrOpen = false;
    let linkExpired = false;
    let expiryInterval = null;
    const platform = detectPlatform();

    function disableExpiredActions() {
        linkExpired = true;
        hideQr();
        [openBtn, downloadBtn, qrBtn, qrFullscreenBtn, qrDownloadBtn, qrDialogDownload].forEach((el) => {
            setDisabled(el, true);
        });
        if (expiryBadge) expiryBadge.classList.add("sub-badge--expired");
        if (expiryText) expiryText.textContent = "Время действия ссылки истекло. Попросите администратора прислать новую.";
        showActionFeedback("Конфигурацию больше нельзя скачать по этой ссылке.");
    }

    function updateExpiryTimer() {
        if (!temporary || !expiresAt || linkExpired) return;
        const remaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
        if (remaining <= 0) {
            if (expiryInterval) window.clearInterval(expiryInterval);
            disableExpiredActions();
            return;
        }
        const minutes = Math.floor(remaining / 60);
        const seconds = String(remaining % 60).padStart(2, "0");
        if (expiryTimer) expiryTimer.textContent = `${minutes}:${seconds}`;
    }

    function applyFamilyStats() {
        const statsMap = state.stats || {};
        const familyStats = statsMap[selectedFamily] || {};
        const profileStats = (familyStats.by_profile || {})[selectedProfile] || familyStats;
        const trafficEl = document.getElementById("subStatTraffic");
        const seenEl = document.getElementById("subStatLastSeen");
        const statusEl = document.getElementById("subStatStatus");
        if (trafficEl) trafficEl.textContent = familyStats.traffic_total || "—";
        if (seenEl) seenEl.textContent = familyStats.last_seen || "—";
        if (statusEl) {
            statusEl.textContent = profileStats.status_label || familyStats.status_label || "—";
            ["ok", "online", "offline", "blocked", "expired", "expiring", "unknown"].forEach((kind) => {
                statusEl.classList.remove(`sub-stat-value--${kind}`);
            });
            const kind = profileStats.status_kind || familyStats.status_kind;
            if (kind) statusEl.classList.add(`sub-stat-value--${kind}`);
        }
    }

    function applySelection() {
        applyFamilyStats();
        const availableFamilies = new Set(items.map((item) => familyOfApp(appOf(item))));
        familyButtons.forEach((btn) => {
            const available = availableFamilies.has(btn.dataset.family);
            btn.hidden = !available;
            btn.classList.toggle("d-none", !available);
            const active = available && btn.dataset.family === selectedFamily;
            btn.classList.toggle("active", active);
            btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (familyTabs) {
            familyTabs.hidden = availableFamilies.size <= 1;
            familyTabs.classList.toggle("d-none", availableFamilies.size <= 1);
        }

        const familyApps = new Set(appsForFamily(selectedFamily));
        setChoiceButtons(appButtons, familyApps, "app", selectedApp);
        document.getElementById("subAppType").classList.toggle("d-none", familyApps.size <= 1);

        const availableProfiles = new Set(profilesFor(selectedApp));
        setChoiceButtons(profileButtons, availableProfiles, "profile", selectedProfile);
        if (profileWrap) profileWrap.hidden = availableProfiles.size <= 1;

        const isOpenVpn = selectedApp === "openvpn";
        const availableProtocols = new Set(isOpenVpn ? protocolsFor(selectedApp, selectedProfile) : []);
        setChoiceButtons(protocolButtons, availableProtocols, "protocol", selectedProtocol);
        if (protocolWrap) {
            protocolWrap.hidden = !isOpenVpn || availableProtocols.size <= 1;
        }
        if (protocolAdvanced && selectedProtocol && selectedProtocol !== "auto") {
            protocolAdvanced.open = true;
        }

        const meta = appMeta[selectedApp] || appMeta.openvpn;
        const currentLink = meta.links[platform] || meta.links.other;
        const platformName = platformLabel(platform);
        if (appStepTitle) {
            appStepTitle.textContent = familyApps.size > 1
                ? "Выберите приложение"
                : `Приложение: ${meta.shortName || meta.title}`;
        }
        if (appDownload) {
            appDownload.href = currentLink.href;
            const appName = meta.shortName || meta.title;
            const text = platformName
                ? `Скачать ${appName} для ${platformName}`
                : `Скачать ${appName}`;
            appDownload.innerHTML = `${platformIconHtml(platform)}<span>${text}</span>`;
        }
        if (appHint) {
            appHint.textContent = "";
            appHint.hidden = true;
        }
        if (otherLinks) {
            otherLinks.innerHTML = "";
            Object.keys(meta.links).forEach((key) => {
                if (key === platform) return;
                if (key === "other" && selectedFamily === "wireguard") return;
                if (key === "other" && currentLink === meta.links.other) return;
                const link = meta.links[key];
                const a = document.createElement("a");
                a.href = link.href;
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.innerHTML = `${platformIconHtml(key)}<span>${link.label}</span>`;
                otherLinks.appendChild(a);
            });
        }
        if (howTo) {
            howTo.innerHTML = "";
            meta.how.forEach((line) => {
                const li = document.createElement("li");
                li.textContent = line;
                howTo.appendChild(li);
            });
        }
        if (step2Desc) {
            step2Desc.textContent = selectedApp === "openvpn"
                ? `Выберите режим и откройте профиль в ${meta.title}.`
                : `Выберите режим и импортируйте конфигурацию в ${meta.title}.`;
        }

        const item = findItem();
        if (!item) {
            setLink(openBtn, null);
            setLink(downloadBtn, null);
            openBtn.removeAttribute("download");
            downloadBtn.removeAttribute("download");
            downloadBtn.classList.add("d-none");
            if (qrBtn) qrBtn.classList.add("d-none");
            hideQr();
            return;
        }

        const url = fileUrl(item);
        const fileName = item.filename || `${item.slug}.${item.ext || (isOpenVpn ? "ovpn" : "conf")}`;

        if (isOpenVpn) {
            openBtn.classList.remove("d-none");
            openBtn.removeAttribute("download");
            openBtn.textContent = "Открыть в OpenVPN Connect";
            setLink(openBtn, "openvpn://import-profile/" + url);
            downloadBtn.classList.remove("d-none");
            downloadBtn.setAttribute("download", fileName);
            setLink(downloadBtn, url);
            if (qrBtn) qrBtn.classList.add("d-none");
            hideQr();
        } else {
            openBtn.classList.remove("d-none");
            openBtn.textContent = "Скачать конфигурацию";
            openBtn.setAttribute("download", fileName);
            setLink(openBtn, url);
            downloadBtn.classList.add("d-none");
            downloadBtn.removeAttribute("download");
            setLink(downloadBtn, null);
            if (qrBtn) qrBtn.classList.remove("d-none");
            if (qrOpen && qrImg) {
                setQrSource(item);
                qrWrap.hidden = false;
                qrWrap.classList.remove("d-none");
            }
        }

        if (linkExpired) {
            [openBtn, downloadBtn, qrBtn, qrFullscreenBtn, qrDownloadBtn, qrDialogDownload].forEach((el) => {
                setDisabled(el, true);
            });
        }
    }

    const availableFamilies = new Set(items.map((item) => familyOfApp(appOf(item))));
    applyFamilyDefaults(availableFamilies.has("openvpn") ? "openvpn" : "wireguard");
    applySelection();
    updateExpiryTimer();
    if (temporary && expiresAt && !linkExpired) {
        expiryInterval = window.setInterval(updateExpiryTimer, 1000);
    }

    familyButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const family = btn.dataset.family;
            if (!appsForFamily(family).length) return;
            applyFamilyDefaults(family);
            hideQr();
            hideActionFeedback();
            applySelection();
        });
    });

    appButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.disabled) return;
            selectedApp = btn.dataset.app;
            selectedFamily = familyOfApp(selectedApp);
            selectedProfile = chooseValue(profilesFor(selectedApp), selectedProfile, ["antizapret", "vpn"]);
            selectedProtocol = chooseValue(protocolsFor(selectedApp, selectedProfile), selectedProtocol, ["auto", "tcp", "udp"]);
            hideQr();
            hideActionFeedback();
            applySelection();
        });
    });

    profileButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.disabled) return;
            selectedProfile = btn.dataset.profile;
            selectedProtocol = chooseValue(protocolsFor(selectedApp, selectedProfile), selectedProtocol, ["auto", "tcp", "udp"]);
            hideActionFeedback();
            applySelection();
        });
    });

    protocolButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            if (btn.disabled) return;
            selectedProtocol = btn.dataset.protocol;
            hideActionFeedback();
            applySelection();
        });
    });

    if (qrBtn) {
        qrBtn.addEventListener("click", () => {
            if (linkExpired) return;
            const item = findItem();
            if (!item || appOf(item) === "openvpn") return;
            qrOpen = !qrOpen;
            if (!qrOpen) {
                hideQr();
                return;
            }
            setQrSource(item);
            if (qrWrap) {
                qrWrap.hidden = false;
                qrWrap.classList.remove("d-none");
            }
            qrBtn.textContent = "Скрыть QR-код";
        });
    }

    if (openBtn) {
        openBtn.addEventListener("click", () => {
            if (linkExpired) return;
            const item = findItem();
            if (!item) return;
            if (appOf(item) === "openvpn") {
                showActionFeedback("Если OpenVPN Connect не открылся, скачайте файл кнопкой ниже и импортируйте его вручную.");
            } else {
                showActionFeedback("Файл скачан. Откройте его в WireGuard или AmneziaWG для импорта туннеля.");
            }
        });
    }

    if (downloadBtn) {
        downloadBtn.addEventListener("click", () => {
            if (linkExpired) return;
            showActionFeedback("Файл скачан. Откройте приложение и импортируйте сохранённую конфигурацию.");
        });
    }

    if (qrFullscreenBtn) {
        qrFullscreenBtn.addEventListener("click", () => {
            if (linkExpired) return;
            const item = findItem();
            if (!item || appOf(item) === "openvpn" || !qrDialog) return;
            setQrSource(item);
            if (typeof qrDialog.showModal === "function") qrDialog.showModal();
        });
    }

    if (qrDialogClose && qrDialog) {
        qrDialogClose.addEventListener("click", () => qrDialog.close());
        qrDialog.addEventListener("click", (event) => {
            if (event.target === qrDialog) qrDialog.close();
        });
    }
});
