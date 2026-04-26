let clientChart = null;
let selectedClients = [];
let selectedChartPeriod = 'day';
const OVPN_STORAGE_KEY = 'ovpnStats.selectedClient';
const MULTI_MAX_CLIENTS = 5;
const MULTI_COLORS = ['#4e79a7', '#e15759', '#76b7b2', '#f28e2b', '#59a14f'];
let chartRawLabels = [];
let chartRxSeries = [];
let chartTxSeries = [];
let chartDateOverride = null;

function getClientTimezone() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch (e) {
        return '';
    }
}

function getEffectiveTimezone() {
    const fromUrl = new URLSearchParams(window.location.search).get('tz');
    return fromUrl || getClientTimezone();
}

function ensureTimezoneInUrl() {
    const browserTz = getClientTimezone();
    if (!browserTz) return false;
    const url = new URL(window.location.href);
    const currentTz = url.searchParams.get('tz');
    if (currentTz === browserTz) return false;
    url.searchParams.set('tz', browserTz);
    window.location.replace(url.toString());
    return true;
}

function ymd(dateObj) {
    return dateObj.toISOString().slice(0, 10);
}

function getPeriodParams(period, overrideRange = null) {
    const params = new URLSearchParams({ period });
    const pageParams = new URLSearchParams(window.location.search);
    const tz = getEffectiveTimezone();
    if (tz) params.set('tz', tz);
    if (overrideRange && overrideRange.from && overrideRange.to) {
        params.set('period', 'custom');
        params.set('date_from', overrideRange.from);
        params.set('date_to', overrideRange.to);
        return params;
    }
    if (period === 'custom' || period === 'month') {
        const dateFrom = pageParams.get('date_from');
        const dateTo = pageParams.get('date_to');
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);
    }
    return params;
}

function getEffectivePeriod(period, params) {
    if (period !== 'custom') return period;
    const from = params.get('date_from');
    const to = params.get('date_to');
    if (!from || !to) return 'day';
    if (from && to && from === to) return 'day';
    return 'custom';
}

function isMultiMode() {
    const toggle = document.getElementById('multiSelectToggle');
    return !!(toggle && toggle.checked);
}

function getActiveClientName() {
    return selectedClients.length ? selectedClients[0] : null;
}

function persistSelectedClients() {
    try {
        localStorage.setItem(OVPN_STORAGE_KEY, JSON.stringify(selectedClients));
    } catch (e) {}
}

function updateRowSelectionUI() {
    document.querySelectorAll('.client-table tbody tr').forEach((r) => {
        r.classList.toggle('table-active', selectedClients.includes(r.dataset.client));
    });
}

function updateKpi(rx, tx) {
    const totalNow = rx.reduce((a, b) => a + b, 0) + tx.reduce((a, b) => a + b, 0);
    const points = Math.max(rx.length, 1);
    const avg = totalNow / points;
    const peak = rx.map((v, i) => v + (tx[i] || 0)).reduce((a, b) => Math.max(a, b), 0);

    const totalEl = document.getElementById('chartKpiTotal');
    const avgEl = document.getElementById('chartKpiAvg');
    const peakEl = document.getElementById('chartKpiPeak');
    if (totalEl) totalEl.textContent = `Итого: ${humanizeBytes(totalNow)}`;
    if (avgEl) avgEl.textContent = `Среднее: ${humanizeBytes(avg)}`;
    if (peakEl) peakEl.textContent = `Пик: ${humanizeBytes(peak)}`;
}

function setChartLoading(isLoading) {
    const wrap = document.getElementById('clientChartWrap');
    if (!wrap) return;
    wrap.classList.toggle('is-loading', !!isLoading);
}

function formatDateRu(ymdValue) {
    const d = new Date(`${ymdValue}T00:00:00`);
    if (Number.isNaN(d.getTime())) return ymdValue;
    return d.toLocaleDateString('ru-RU');
}

function updateChartPeriodLabel(effectivePeriod, params) {
    const labelEl = document.getElementById('chartPeriodLabel');
    if (!labelEl) return;

    let text = '';
    if (effectivePeriod === 'day') {
        const day = params.get('date_from') || new URLSearchParams(window.location.search).get('date_from');
        if (day) {
            text = `за ${formatDateRu(day)}`;
        }
    } else if (effectivePeriod === 'month') {
        const from = params.get('date_from') || new URLSearchParams(window.location.search).get('date_from');
        if (from) {
            const d = new Date(`${from}T00:00:00`);
            if (!Number.isNaN(d.getTime())) {
                text = d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
            }
        }
    } else if (effectivePeriod === 'year') {
        const from = params.get('date_from') || new URLSearchParams(window.location.search).get('date_from');
        if (from) {
            text = from.slice(0, 4);
        }
    } else {
        const from = params.get('date_from');
        const to = params.get('date_to');
        if (from && to) {
            text = from === to
                ? `за ${formatDateRu(from)}`
                : `с ${formatDateRu(from)} по ${formatDateRu(to)}`;
        }
    }

    if (text) {
        labelEl.textContent = text;
    }
}

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
    if (period === 'day') {
        const parts = dateStr.split(' ');
        if (parts.length >= 2) {
            return parts[1];
        }
        return dateStr;
    }
    if (period === 'year') {
        const parts = dateStr.split('-');
        if (parts.length >= 2) {
            const names = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
            const idx = parseInt(parts[1], 10) - 1;
            if (idx >= 0 && idx < 12) return names[idx] + ' ' + parts[0];
        }
        return dateStr;
    }
    const d = new Date(dateStr + 'T00:00:00');
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

async function updateClientChart() {
    const activeClient = getActiveClientName();
    if (!activeClient) return;

    const basePath = window.basePath || '';
    const params = getPeriodParams(selectedChartPeriod, chartDateOverride);
    params.set('client', activeClient);
    const effectivePeriod = getEffectivePeriod(selectedChartPeriod, params);
    setChartLoading(true);
    try {
        const multiMode = isMultiMode();
        const targetClients = multiMode ? selectedClients.slice(0, MULTI_MAX_CLIENTS) : [activeClient];
        const responses = await Promise.all(
            targetClients.map(async (clientName) => {
                const p = getPeriodParams(selectedChartPeriod, chartDateOverride);
                p.set('client', clientName);
                const res = await fetch(`${basePath}/api/ovpn/client_chart?${p.toString()}`);
                const data = await res.json();
                return { clientName, data };
            })
        );
        if (!responses.length || responses[0].data.error) {
            console.error(responses[0]?.data?.error || 'No data');
            return;
        }

        chartRawLabels = responses[0].data.labels.slice();
        const labels = chartRawLabels.map(l => formatLabel(l, effectivePeriod));
        const colors = getThemeColors();
        const xAxisTitle = (effectivePeriod === 'day') ? 'Время' : 'Дата';
        updateChartPeriodLabel(effectivePeriod, params);
        let datasets = [];

        if (multiMode) {
            const combinedByClient = responses.map(({ clientName, data }, idx) => {
                const series = chartRawLabels.map((label) => {
                    const i = data.labels.indexOf(label);
                    return i >= 0 ? (data.rx_bytes[i] || 0) + (data.tx_bytes[i] || 0) : 0;
                });
                return { clientName, series, idx };
            });
            const aggregate = chartRawLabels.map((_, i) =>
                combinedByClient.reduce((acc, s) => acc + (s.series[i] || 0), 0)
            );
            chartRxSeries = aggregate.slice();
            chartTxSeries = new Array(aggregate.length).fill(0);
            datasets = combinedByClient.map((item) => ({
                label: `${item.clientName}`,
                data: item.series,
                fill: false,
                borderColor: MULTI_COLORS[item.idx % MULTI_COLORS.length],
                backgroundColor: MULTI_COLORS[item.idx % MULTI_COLORS.length],
                tension: 0.2,
                pointRadius: 2
            }));
            updateKpi(aggregate, []);
        } else {
            const data = responses[0].data;
            chartRxSeries = data.rx_bytes.slice();
            chartTxSeries = data.tx_bytes.slice();
            datasets = [
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
            updateKpi(data.rx_bytes, data.tx_bytes);
        }

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
                    onClick: function (_, elements) {
                        if (!elements.length) return;
                        if (!chartRawLabels.length) return;
                        if (effectivePeriod === 'day') return;
                        const pointIndex = elements[0].index;
                        const clicked = chartRawLabels[pointIndex];
                        if (!clicked) return;
                        if (effectivePeriod === 'year') {
                            const [yy, mm] = clicked.split('-');
                            const start = new Date(Number(yy), Number(mm) - 1, 1);
                            const end = new Date(Number(yy), Number(mm), 0);
                            chartDateOverride = { from: ymd(start), to: ymd(end) };
                        } else {
                            chartDateOverride = { from: clicked.slice(0, 10), to: clicked.slice(0, 10) };
                        }
                        selectedChartPeriod = 'custom';
                        updateClientChart();
                    },
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
    } finally {
        setChartLoading(false);
    }
}

function selectClient(clientName) {
    const container = document.getElementById('clientChartContainer');
    const nameEl = document.getElementById('chartClientName');

    if (isMultiMode()) {
        if (selectedClients.includes(clientName)) {
            selectedClients = selectedClients.filter((c) => c !== clientName);
        } else {
            if (selectedClients.length >= MULTI_MAX_CLIENTS) {
                alert(`Можно выбрать максимум ${MULTI_MAX_CLIENTS} клиентов`);
                return;
            }
            selectedClients.push(clientName);
        }
        persistSelectedClients();
    } else {
        if (getActiveClientName() === clientName) {
            selectedClients = [];
            try { localStorage.removeItem(OVPN_STORAGE_KEY); } catch (e) { }
        } else {
            selectedClients = [clientName];
            persistSelectedClients();
        }
    }

    if (!selectedClients.length) {
        container.style.display = 'none';
        updateRowSelectionUI();
        if (clientChart) {
            clientChart.destroy();
            clientChart = null;
        }
        return;
    }

    nameEl.textContent = isMultiMode()
        ? selectedClients.join(', ')
        : selectedClients[0];
    container.style.display = 'block';
    updateRowSelectionUI();

    if (clientChart) {
        clientChart.destroy();
        clientChart = null;
    }

    setTimeout(() => {
        updateClientChart();
        container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 10);
}

function downloadCsv() {
    if (!chartRawLabels.length) return;
    const lines = ['label,rx_bytes,tx_bytes,total_bytes'];
    chartRawLabels.forEach((label, idx) => {
        const rx = chartRxSeries[idx] || 0;
        const tx = chartTxSeries[idx] || 0;
        lines.push(`${label},${rx},${tx},${rx + tx}`);
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ovpn-${(isMultiMode() ? 'multi' : (getActiveClientName() || 'client'))}-chart.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

document.addEventListener('DOMContentLoaded', () => {
    if (ensureTimezoneInUrl()) {
        return;
    }

    const tzInput = document.getElementById('statsClientTz');
    if (tzInput && !tzInput.value) {
        tzInput.value = getEffectiveTimezone();
    }

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

    // Быстрые интервалы (последние 7/30/365 дней) из dropdown с иконкой часов.
    const quickRangeLinks = document.querySelectorAll('.stats-quick-range[data-days]');
    const offscreenForm = document.querySelector('.stats-date-range-offscreen form');
    const toLocalYmd = (d) => {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    };

    if (quickRangeLinks.length && offscreenForm && dateFromInput && dateToInput) {
        quickRangeLinks.forEach((link) => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const days = parseInt(link.dataset.days || '0', 10);
                if (!days || days < 1) return;

                const end = new Date();
                const start = new Date(end);
                start.setDate(end.getDate() - (days - 1));

                dateFromInput.value = toLocalYmd(start);
                dateToInput.value = toLocalYmd(end);

                // offscreen form имеет method="get" и period=custom, сервер сам пересчитает интервал.
                offscreenForm.submit();
            });
        });
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

    const multiToggle = document.getElementById('multiSelectToggle');
    if (multiToggle) {
        multiToggle.addEventListener('change', () => {
            if (!multiToggle.checked && selectedClients.length > 1) {
                selectedClients = selectedClients.slice(0, 1);
                persistSelectedClients();
            }
            const container = document.getElementById('clientChartContainer');
            const nameEl = document.getElementById('chartClientName');
            if (selectedClients.length) {
                container.style.display = 'block';
                nameEl.textContent = multiToggle.checked ? selectedClients.join(', ') : selectedClients[0];
                updateRowSelectionUI();
                updateClientChart();
            } else {
                updateRowSelectionUI();
            }
        });
    }

    const pngBtn = document.getElementById('exportChartPngBtn');
    if (pngBtn) {
        pngBtn.addEventListener('click', () => {
            if (!clientChart) return;
            const a = document.createElement('a');
            a.href = clientChart.toBase64Image();
            a.download = `ovpn-${(isMultiMode() ? 'multi' : (getActiveClientName() || 'client'))}-chart.png`;
            a.click();
        });
    }
    const csvBtn = document.getElementById('exportChartCsvBtn');
    if (csvBtn) {
        csvBtn.addEventListener('click', downloadCsv);
    }

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
        const savedRaw = localStorage.getItem(OVPN_STORAGE_KEY);
        if (savedRaw) {
            let parsed = [];
            try {
                const maybeArray = JSON.parse(savedRaw);
                if (Array.isArray(maybeArray)) parsed = maybeArray;
                else if (typeof maybeArray === 'string' && maybeArray) parsed = [maybeArray];
            } catch (_) {
                parsed = [savedRaw];
            }
            selectedClients = parsed
                .filter((name) => document.querySelector(`.client-table tbody tr[data-client="${name}"]`))
                .slice(0, MULTI_MAX_CLIENTS);
            if (!isMultiMode() && selectedClients.length > 1) {
                selectedClients = selectedClients.slice(0, 1);
            }
            if (selectedClients.length) {
                const container = document.getElementById('clientChartContainer');
                const nameEl = document.getElementById('chartClientName');
                container.style.display = 'block';
                nameEl.textContent = (isMultiMode() && selectedClients.length > 1)
                    ? selectedClients.join(', ')
                    : selectedClients[0];
                updateRowSelectionUI();
                updateClientChart();
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
