document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.connection-time[data-utc]').forEach(cell => {
        const utcDate = new Date(cell.dataset.utc);
        cell.textContent = utcDate.toLocaleString(undefined, {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    });

    // Фильтр
    const clientFilter = document.getElementById("clientFilter"); 

    clientFilter.addEventListener("input", function () {
        const filterValue = clientFilter.value.toLowerCase();

        document.querySelectorAll(".client-table tbody tr").forEach(row => {
            const clientName = row.querySelector(".client-name").textContent.toLowerCase();
            row.style.display = clientName.includes(filterValue) ? "" : "none";
        });
    });
});
