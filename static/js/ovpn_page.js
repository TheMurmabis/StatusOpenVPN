document.addEventListener("DOMContentLoaded", () => {
    const showColumnsCheckbox = document.getElementById("show-columns-checkbox");
    const speedColumns = document.querySelectorAll(".speed-column");
    const savedShowColumnsState = localStorage.getItem("showColumns");

    if (savedShowColumnsState === "true") {
        showColumnsCheckbox.checked = true;
        toggleColumns(true);
    } else {
        showColumnsCheckbox.checked = false;
        toggleColumns(false);
    }

    showColumnsCheckbox.addEventListener("change", () => {
        toggleColumns(showColumnsCheckbox.checked);
        localStorage.setItem("showColumns", showColumnsCheckbox.checked);
    });

    function toggleColumns(showColumns) {
        speedColumns.forEach(column => column.classList.toggle("hidden", !showColumns));
    }

    function convertToUserTimezone() {
        const timeCells = document.querySelectorAll('.connection-time');

        timeCells.forEach(cell => {
            const utcDateStr = cell.getAttribute('data-utc');
            if (utcDateStr) {
                const utcDate = new Date(utcDateStr);
                const localDateString = utcDate.toLocaleString();
                cell.textContent = localDateString;
            }
        });
    }

    convertToUserTimezone();
});
