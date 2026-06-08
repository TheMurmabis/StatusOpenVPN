(function () {
    var pollInterval = 4000;
    var logEl = document.getElementById("updateLog");
    var logPanel = document.getElementById("updateLogPanel");
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
                    setTimeout(poll, pollInterval);
                }
            })
            .catch(function () { /* ignore */ });
    }

    if (logEl.textContent.trim() || document.querySelector(".spinner-border")) {
        setTimeout(poll, pollInterval);
    }
})();
