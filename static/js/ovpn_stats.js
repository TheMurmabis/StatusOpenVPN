let clientChart = null;
let selectedClient = null;
let selectedChartPeriod = 'month';
const OVPN_STORAGE_KEY = 'ovpnStats.selectedClient';

function attachCalendarWheelNavigation(fpInstance) {
    if (!fpInstance || !fpInstance.calendarContainer) return;
    const container = fpInstance.calendarContainer;
    if (container.dataset.navBound === '1') return;

    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        if (e.deltaY > 0) {
            fpInstance.changeMonth(1);
        } else if (e.deltaY < 0) {
            fpInstance.changeMonth(-1);
        }
    }, { passive: false });

    let touchStartX = null;
    let touchStartY = null;
    const minSwipeDistance = 35;

    container.addEventListener('touchstart', (e) => {
        const touch = e.changedTouches && e.changedTouches[0];
        if (!touch) return;
        touchStartX = touch.clientX;
        touchStartY = touch.clientY;
    }, { passive: true });

    container.addEventListener('touchend', (e) => {
        if (touchStartX === null || touchStartY === null) return;
        const touch = e.changedTouches && e.changedTouches[0];
        if (!touch) return;

        const deltaX = touch.clientX - touchStartX;
        const deltaY = touch.clientY - touchStartY;

        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) >= minSwipeDistance) {
            if (deltaX < 0) {
                fpInstance.changeMonth(1);
            } else {
                fpInstance.changeMonth(-1);
            }
        }

        touchStartX = null;
        touchStartY = null;
    }, { passive: true });

    container.dataset.navBound = '1';
}
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
    if (period === 'day') {
        return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
    }
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

async function updateClientChart() {
    if (!selectedClient) return;

    const basePath = window.basePath || '';
    const params = new URLSearchParams({
        client: selectedClient,
        period: selectedChartPeriod
    });
    if (selectedChartPeriod === 'custom') {
        const pageParams = new URLSearchParams(window.location.search);
        const dateFrom = pageParams.get('date_from');
        const dateTo = pageParams.get('date_to');
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);
    } else if (selectedChartPeriod === 'month') {
        const pageParams = new URLSearchParams(window.location.search);
        const dateFrom = pageParams.get('date_from');
        const dateTo = pageParams.get('date_to');
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);
    }
    try {
        const res = await fetch(
            `${basePath}/api/ovpn/client_chart?${params.toString()}`
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
        try { localStorage.removeItem(OVPN_STORAGE_KEY); } catch (e) { }
        container.style.display = 'none';
        document.querySelectorAll('.client-table tbody tr').forEach(r => r.classList.remove('table-active'));
        if (clientChart) {
            clientChart.destroy();
            clientChart = null;
        }
        return;
    }

    selectedClient = clientName;
    try { localStorage.setItem(OVPN_STORAGE_KEY, clientName); } catch (e) { }
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
    const rangeInput = document.getElementById('statsDateRange');
    const dateFromInput = document.getElementById('statsDateFrom');
    const dateToInput = document.getElementById('statsDateTo');
    const calendarOpenBtn = document.getElementById('statsDateRangeOpen');
    if (rangeInput && dateFromInput && dateToInput && typeof flatpickr !== 'undefined') {
        const defaultDates = [];
        if (dateFromInput.value) defaultDates.push(dateFromInput.value);
        if (dateToInput.value) defaultDates.push(dateToInput.value);

        flatpickr.localize(flatpickr.l10ns.ru);
        const fp = flatpickr("#statsDateRange", {
            mode: 'range',
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'd.m.Y',
            locale: { ...flatpickr.l10ns.ru, rangeSeparator: ' — ' },
            maxDate: "today",
            monthSelectorType: "static",
            prevArrow: "<span>&lt;</span>",
            nextArrow: "<span>&gt;</span>",
            defaultDate: defaultDates,
            positionElement: calendarOpenBtn || rangeInput,
            onChange: function (selectedDates, dateStr, instance) {
                if (selectedDates.length < 2) {
                    return;
                }
                const [startDate, endDate] = selectedDates;
                const formatDate = (d) => instance.formatDate(d, 'Y-m-d');
                dateFromInput.value = formatDate(startDate);
                dateToInput.value = formatDate(endDate);
                updateClientChart();
                if (instance.input.form) {
                    instance.input.form.submit();
                }
            }
        });
        if (calendarOpenBtn && fp) {
            calendarOpenBtn.addEventListener('click', (e) => {
                e.preventDefault();
                fp.open();
            });
        }
        attachCalendarWheelNavigation(fp);
    }

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

    // Инициализация периода графика по активной кнопке или URL
    const activePeriodBtn = document.querySelector('.chart-period.active');
    if (activePeriodBtn && activePeriodBtn.dataset.period) {
        selectedChartPeriod = activePeriodBtn.dataset.period;
    } else {
        const urlPeriod = new URLSearchParams(window.location.search).get('period');
        if (urlPeriod) {
            selectedChartPeriod = urlPeriod;
        }
    }

    // Обработчики переключения периода (кнопки около фильтра)
    document.querySelectorAll('.chart-period').forEach(btn => {
        btn.addEventListener('click', function (e) {
            // таблица и так перезагрузится через переход по ссылке,
            // но для сохранения периода на графике обновляем локальное состояние
            selectedChartPeriod = this.dataset.period || selectedChartPeriod;
        });
    });

    // Восстановление последнего выбранного клиента после перезагрузки/смены периода
    try {
        const savedClient = localStorage.getItem(OVPN_STORAGE_KEY);
        if (savedClient) {
            const row = document.querySelector(`.client-table tbody tr[data-client="${savedClient}"]`);
            if (row) {
                // selectedClient ещё null, поэтому selectClient просто откроет график
                selectClient(savedClient);
            }
        }
    } catch (e) {
        console.warn('Не удалось восстановить выбранного клиента OVPN:', e);
    }

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (clientChart) {
            clientChart.destroy();
            clientChart = null;
            updateClientChart();
        }
    });
});
