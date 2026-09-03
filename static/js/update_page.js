(function () {
    var pollInterval = 4000;
    var logEl = document.getElementById("updateLog");
    var logPanel = document.getElementById("updateLogPanel");
    var statusEl = document.getElementById("updateStatusText");
    var runtimeErrorEl = document.getElementById("updateRuntimeError");
    var stayOnPageEl = document.getElementById("updateStayOnPage");
    var copyBtn = document.getElementById("updateLogCopyBtn");
    var downloadBtn = document.getElementById("updateLogDownloadBtn");
    var updateForm = document.getElementById("updateForm");
    var installBodyEl = document.getElementById("updateInstallBody");
    var currentVersionEl = document.getElementById("updateCurrentVersion");
    var latestVersionEl = document.getElementById("updateLatestVersion");
    var availableBadgeEl = document.getElementById("updateAvailableBadge");
    if (!logEl) return;

    var ANSI_COLORS = {
        30: "ansi-black", 31: "ansi-red", 32: "ansi-green", 33: "ansi-yellow",
        34: "ansi-blue", 35: "ansi-magenta", 36: "ansi-cyan", 37: "ansi-white",
        90: "ansi-bright-black", 91: "ansi-bright-red", 92: "ansi-bright-green",
        93: "ansi-bright-yellow", 94: "ansi-bright-blue", 95: "ansi-bright-magenta",
        96: "ansi-bright-cyan", 97: "ansi-bright-white"
    };

    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function xterm256(n) {
        if (n < 16) {
            var base = [
                "#000000", "#cd3131", "#0dbc79", "#e5e510",
                "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
                "#666666", "#f14c4c", "#23d18b", "#f5f543",
                "#3b8eea", "#d670d6", "#29b8db", "#ffffff"
            ];
            return base[n];
        }
        if (n >= 232) {
            var gray = 8 + (n - 232) * 10;
            return "rgb(" + gray + "," + gray + "," + gray + ")";
        }
        var levels = [0, 95, 135, 175, 215, 255];
        var idx = n - 16;
        var r = levels[Math.floor(idx / 36) % 6];
        var g = levels[Math.floor(idx / 6) % 6];
        var b = levels[idx % 6];
        return "rgb(" + r + "," + g + "," + b + ")";
    }

    function ansiToHtml(text) {
        text = text.replace(/\r\n/g, "\n").replace(/\r/g, "");
        var re = /\x1b\[([0-9;]*)m/g;
        var html = "";
        var lastIndex = 0;
        var match;
        var state = { colorClass: null, color: null, bold: false, underline: false };

        function wrap(chunk) {
            if (!chunk) return "";
            var esc = escapeHtml(chunk);
            var classes = [];
            if (state.colorClass) classes.push(state.colorClass);
            if (state.bold) classes.push("ansi-bold");
            if (state.underline) classes.push("ansi-underline");
            var style = state.color ? ' style="color:' + state.color + '"' : "";
            if (!classes.length && !style) return esc;
            return '<span class="' + classes.join(" ") + '"' + style + ">" + esc + "</span>";
        }

        while ((match = re.exec(text)) !== null) {
            html += wrap(text.slice(lastIndex, match.index));
            lastIndex = re.lastIndex;

            var raw = match[1] === "" ? "0" : match[1];
            var codes = raw.split(";");
            for (var i = 0; i < codes.length; i++) {
                var code = parseInt(codes[i], 10);
                if (isNaN(code) || code === 0) {
                    state = { colorClass: null, color: null, bold: false, underline: false };
                } else if (code === 1) {
                    state.bold = true;
                } else if (code === 4) {
                    state.underline = true;
                } else if (code === 22) {
                    state.bold = false;
                } else if (code === 24) {
                    state.underline = false;
                } else if (code === 39) {
                    state.colorClass = null;
                    state.color = null;
                } else if (code === 38 && codes[i + 1] === "5") {
                    state.colorClass = null;
                    state.color = xterm256(parseInt(codes[i + 2], 10));
                    i += 2;
                } else if (ANSI_COLORS[code]) {
                    state.colorClass = ANSI_COLORS[code];
                    state.color = null;
                }
            }
        }
        html += wrap(text.slice(lastIndex));
        return html;
    }

    function render(text) {
        var atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 8;
        logEl.innerHTML = ansiToHtml(text);
        if (atBottom) logEl.scrollTop = logEl.scrollHeight;
    }

    render(logEl.textContent);

    function setStatus(text) {
        if (statusEl) statusEl.textContent = text;
    }

    function getLastLine(text) {
        if (!text) return "";
        var lines = text.replace(/\r\n/g, "\n").split("\n");
        for (var i = lines.length - 1; i >= 0; i--) {
            var value = lines[i].trim();
            if (value) return value;
        }
        return "";
    }

    function setVersionClasses(el, mode) {
        if (!el) return;
        el.classList.remove(
            "update-version--match",
            "update-version--current",
            "update-version--new"
        );
        el.classList.add("update-version--" + mode);
    }

    function hideRunningIndicators() {
        var spinner = document.getElementById("updateRunningSpinner");
        var runningText = document.getElementById("updateRunningText");
        if (spinner) spinner.classList.add("d-none");
        if (runningText) runningText.classList.add("d-none");
        document.querySelectorAll("#updateInstallBody .spinner-border").forEach(function (el) {
            el.classList.add("d-none");
        });
    }

    function applyFinishedUi(data, failed) {
        hideRunningIndicators();

        var current = data.current_version || "";
        var latest = data.latest_version || "";
        var matched = !!(latest && current && latest === current);

        if (currentVersionEl) {
            currentVersionEl.textContent = current;
            setVersionClasses(currentVersionEl, matched ? "match" : "current");
        }
        if (latestVersionEl) {
            latestVersionEl.textContent = latest || latestVersionEl.textContent;
            setVersionClasses(latestVersionEl, matched ? "match" : (data.update_available ? "new" : "current"));
        }
        if (availableBadgeEl) {
            availableBadgeEl.classList.toggle("d-none", matched || !latest);
        }

        if (installBodyEl) {
            if (failed) {
                installBodyEl.innerHTML =
                    '<p class="small text-danger mb-0">Обновление завершилось с ошибкой. Проверьте журнал.</p>';
            } else if (matched) {
                installBodyEl.innerHTML =
                    '<p class="small text-success mb-0">Установлена последняя версия.</p>';
            } else if (data.update_available && latest) {
                installBodyEl.innerHTML =
                    '<p class="small text-muted mb-3">' +
                    "Обновление выполняется автоматически без дополнительных вопросов: загрузка тега с GitHub, " +
                    "зависимости Python и перезапуск служб. Панель может быть недоступна несколько минут." +
                    "</p>" +
                    '<form method="post" id="updateForm">' +
                    '<button type="submit" class="btn btn-sm btn-primary settings-action-btn">' +
                    '<i class="bi bi-arrow-repeat me-1" aria-hidden="true"></i>' +
                    "Обновить до " + escapeHtml(latest) +
                    "</button></form>";
                updateForm = document.getElementById("updateForm");
                if (updateForm) {
                    updateForm.addEventListener("submit", function () {
                        var btn = updateForm.querySelector("button[type='submit']");
                        if (btn) {
                            btn.disabled = true;
                            btn.setAttribute("aria-disabled", "true");
                        }
                    });
                }
            } else {
                installBodyEl.innerHTML =
                    '<p class="small text-muted mb-0">Новых версий не найдено.</p>';
            }
        }
    }

    var wasRunning = !!document.querySelector(".spinner-border");

    if (updateForm) {
        updateForm.addEventListener("submit", function () {
            var btn = updateForm.querySelector("button[type='submit']");
            if (btn) {
                btn.disabled = true;
                btn.setAttribute("aria-disabled", "true");
            }
        });
    }

    if (copyBtn) {
        copyBtn.addEventListener("click", function () {
            var text = logEl.textContent || "";
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
            }
        });
    }

    if (downloadBtn) {
        downloadBtn.addEventListener("click", function () {
            var text = logEl.textContent || "";
            if (!text) return;
            var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
            var url = window.URL.createObjectURL(blob);
            var link = document.createElement("a");
            link.href = url;
            link.download = "update.log";
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        });
    }

    function poll() {
        var base = window.basePath || "";
        fetch(base + "/api/settings/update/status", { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.log) {
                    render(data.log);
                    if (logPanel) logPanel.style.display = "";
                }
                if (data.running) {
                    wasRunning = true;
                    if (runtimeErrorEl) runtimeErrorEl.classList.add("d-none");
                    var lastLine = getLastLine(data.log || "");
                    setStatus(lastLine || "🔄 Выполняется обновление");
                    setTimeout(poll, pollInterval);
                } else if (wasRunning) {
                    var updateFailed = !!data.update_available;
                    if (updateFailed) {
                        if (runtimeErrorEl) {
                            runtimeErrorEl.textContent = "Обновление завершилось с ошибкой. Проверьте журнал.";
                            runtimeErrorEl.classList.remove("d-none");
                        }
                        setStatus("Ошибка обновления");
                        applyFinishedUi(data, true);
                        wasRunning = false;
                        return;
                    }
                    setStatus("🟢 Установлена последняя версия");
                    applyFinishedUi(data, false);
                    wasRunning = false;
                    if (stayOnPageEl && stayOnPageEl.checked) return;
                    window.location.href = base + "/";
                } else {
                    if (data.update_available) {
                        setStatus("🟡 Доступно обновление");
                    } else if (data.latest_version && data.current_version === data.latest_version) {
                        setStatus("🟢 Установлена последняя версия");
                    } else {
                        setStatus("Нет обновлений");
                    }
                }
            })
            .catch(function () {
                if (wasRunning) {
                    setTimeout(poll, pollInterval);
                }
            });
    }

    if (logEl.textContent.trim() || document.querySelector(".spinner-border")) {
        setTimeout(poll, pollInterval);
    }

    (function syncChangelogChevron() {
        var panel = document.getElementById("updateChangelogCollapse");
        if (!panel) return;
        var sel = '[data-bs-target="#updateChangelogCollapse"]';
        function sync() {
            var expanded = panel.classList.contains("show");
            document.querySelectorAll(sel + ".install-panel-chevron").forEach(function (ch) {
                ch.classList.toggle("collapsed", !expanded);
                ch.setAttribute("aria-expanded", expanded ? "true" : "false");
            });
            document.querySelectorAll(sel + ".install-panel-header__toggle").forEach(function (el) {
                el.setAttribute("aria-expanded", expanded ? "true" : "false");
            });
        }
        panel.addEventListener("shown.bs.collapse", sync);
        panel.addEventListener("hidden.bs.collapse", sync);
    })();
})();
