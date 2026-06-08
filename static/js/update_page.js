(function () {
    var pollInterval = 4000;
    var logEl = document.getElementById("updateLog");
    var logPanel = document.getElementById("updateLogPanel");
    if (!logEl) return;

    function poll() {
        var base = window.basePath || "";
        fetch(base + "/api/settings/update/status", { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.log) {
                    logEl.textContent = data.log;
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
