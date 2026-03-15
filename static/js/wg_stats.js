let clientChart = null;
let selectedClient = null;
let selectedChartPeriod = 'month';
const WG_STORAGE_KEY = 'wgStats.selectedClient';

function getThemeColors() {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    return {
        rx: {
            border: isDark ? 'rgba(100, 181, 246, 1)' : 'rgba(54, 162, 235, 1)',
            fill: isDark ? 'rgba(100, 181, 246, 0.25)' : 'rgba(54, 162, 235, 0.2)'
        },
        tx: {
            border: isDark ? 'rgba(255, 138, 128, 1)' : 'rgba(255, 99, 132, 1)',
            fill: isDark ? 'rgba(255, 138, 128, 0.25)' : 'rgba(255, 99, 132, 0.2)'
        },
        grid: isDark ? '#333' : '#ddd',
        text: isDark ? '#ccc' : '#333'
    };
}

function humanizeBytes(bytes) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
        val /= 1024;
        i++;
    }
    return val.toFixed(2) + ' ' + units[i];
}

function formatLabel(dateStr, period) {
    const d = new Date(dateStr + 'T00:00:00');
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

async function updateClientChart() {
    if (!selectedClient) return;

    const basePath = window.basePath || '';
    try {
        const res = await fetch(
            `${basePath}/api/wg/client_chart?client=${encodeURIComponent(selectedClient)}&period=${selectedChartPeriod}`
        );
        const data = await res.json();
        if (data.error) {
            console.error(data.error);
            return;
        }

        const labels = data.labels.map(l => formatLabel(l, selectedChartPeriod));
        const colors = getThemeColors();
        const xAxisTitle = (selectedChartPeriod === 'day') ? 'Время' : 'Дата';

        const datasets = [
            {
                label: 'Получено',
                data: data.rx_bytes,
                fill: true,
                borderColor: colors.rx.border,
                backgroundColor: colors.rx.fill,
                tension: 0.2,
                pointRadius: 2
            },
            {
                label: 'Передано',
                data: data.tx_bytes,
                fill: true,
                borderColor: colors.tx.border,
                backgroundColor: colors.tx.fill,
                tension: 0.2,
                pointRadius: 2
            }
        ];

        if (clientChart) {
            clientChart.data.labels = labels;
            clientChart.data.datasets = datasets;
            clientChart.options.scales.x.title.text = xAxisTitle;
            clientChart.options.scales.x.title.color = colors.text;
            clientChart.options.scales.y.title.color = colors.text;
            clientChart.options.scales.x.ticks.color = colors.text;
            clientChart.options.scales.y.ticks.color = colors.text;
            clientChart.options.scales.x.grid.color = colors.grid;
            clientChart.options.scales.y.grid.color = colors.grid;
            clientChart.options.plugins.legend.labels.color = colors.text;
            clientChart.update();
        } else {
            const ctx = document.getElementById('clientChart').getContext('2d');
            clientChart = new Chart(ctx, {
                type: 'line',
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: {
                            title: { display: true, text: 'Трафик', color: colors.text },
                            beginAtZero: true,
                            grid: { color: colors.grid },
                            ticks: {
                                color: colors.text,
                                callback: function (value) { return humanizeBytes(value); }
                            }
                        },
                        x: {
                            title: { display: true, text: xAxisTitle, color: colors.text },
                            grid: { color: colors.grid },
                            ticks: { color: colors.text }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: colors.text, usePointStyle: false }
                        },
                        tooltip: {
                            callbacks: {
                                label: function (ctx) {
                                    return `${ctx.dataset.label}: ${humanizeBytes(ctx.parsed.y)}`;
                                }
                            }
                        }
                    }
                }
            });
        }
    } catch (e) {
        console.error('Ошибка при загрузке графика клиента:', e);
    }
}

function selectClient(clientName) {
    const container = document.getElementById('clientChartContainer');
    const nameEl = document.getElementById('chartClientName');

    if (selectedClient === clientName) {
        selectedClient = null;
        try { localStorage.removeItem(WG_STORAGE_KEY); } catch (e) {}
        container.style.display = 'none';
        document.querySelectorAll('.client-table tbody tr').forEach(r => r.classList.remove('table-active'));
        if (clientChart) {
            clientChart.destroy();
            clientChart = null;
        }
        return;
    }

    selectedClient = clientName;
    try { localStorage.setItem(WG_STORAGE_KEY, clientName); } catch (e) {}
    nameEl.textContent = clientName;
    container.style.display = 'block';

    document.querySelectorAll('.client-table tbody tr').forEach(r => {
        r.classList.toggle('table-active', r.dataset.client === clientName);
    });

    if (clientChart) {
        clientChart.destroy();
        clientChart = null;
    }

    setTimeout(() => {
        updateClientChart();
        container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 10);
}

document.addEventListener('DOMContentLoaded', () => {
    const clientFilter = document.getElementById('clientFilter');
    if (clientFilter) {
        clientFilter.addEventListener('input', function () {
            const filterValue = clientFilter.value.toLowerCase();
            document.querySelectorAll('.client-table tbody tr').forEach(row => {
                const clientName = row.querySelector('.client-name').textContent.toLowerCase();
                row.style.display = clientName.includes(filterValue) ? '' : 'none';
            });
        });
    }

    document.querySelectorAll('.client-table tbody tr[data-client]').forEach(row => {
        row.addEventListener('click', () => {
            selectClient(row.dataset.client);
        });
    });

    // Инициализация периода по активной кнопке
    const activePeriodBtn = document.querySelector('.chart-period.active');
    if (activePeriodBtn && activePeriodBtn.dataset.period) {
        selectedChartPeriod = activePeriodBtn.dataset.period;
    }

    // Обновляем только локальное состояние периода (для графика) — таблица перезагрузится сама
    document.querySelectorAll('.chart-period').forEach(btn => {
        btn.addEventListener('click', function () {
            selectedChartPeriod = this.dataset.period || selectedChartPeriod;
        });
    });

    // Восстановление ранее выбранного клиента после перезагрузки/смены периода
    try {
        const savedClient = localStorage.getItem(WG_STORAGE_KEY);
        if (savedClient) {
            const row = document.querySelector(`.client-table tbody tr[data-client="${savedClient}"]`);
            if (row) {
                selectClient(savedClient);
            }
        }
    } catch (e) {
        console.warn('Не удалось восстановить выбранного клиента WG:', e);
    }

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (clientChart) {
            clientChart.destroy();
            clientChart = null;
            updateClientChart();
        }
    });
});
