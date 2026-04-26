// График ЦП и ОЗУ
let cpuChart = null;
let cpuInterval = null;
const LIVE_UPDATE_MS = 5000;

function themeColors() {
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    return {
        cpuBorder: isDark ? 'rgba(255,99,132,1)' : 'rgba(220,53,69,1)',
        cpuFill: isDark ? 'rgba(255,99,132,0.12)' : 'rgba(220,53,69,0.08)',
        ramBorder: isDark ? 'rgba(100,181,246,1)' : 'rgba(54,162,235,1)',
        ramFill: isDark ? 'rgba(100,181,246,0.12)' : 'rgba(54,162,235,0.08)',
        text: isDark ? '#ddd' : '#222',
        grid: isDark ? '#333' : '#eee'
    };
}

function initCpuChart() {
    const ctx = document.getElementById('cpuChart').getContext('2d');
    const colors = themeColors();

    if (cpuChart) {
        cpuChart.destroy();
    }

    cpuChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'ЦП %',
                    data: [],
                    borderColor: colors.cpuBorder,
                    backgroundColor: colors.cpuFill,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    yAxisID: 'y'
                },
                {
                    label: 'ОЗУ %',
                    data: [],
                    borderColor: colors.ramBorder,
                    backgroundColor: colors.ramFill,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    yAxisID: 'y'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { 
                    position: 'bottom',
                    labels: {
                        color: colors.text
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            return `${ctx.dataset.label}: ${ctx.parsed.y}%`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { 
                        display: true, 
                        text: 'Процент',
                        color: colors.text
                    },
                    grid: { color: colors.grid },
                    ticks: {
                        color: colors.text
                    }
                },
                x: {
                    title: { 
                        display: true, 
                        text: 'Время',
                        color: colors.text
                    },
                    grid: { color: colors.grid },
                    ticks: {
                        color: colors.text
                    }
                }
            }
        }
    });
}

function updateCpuChart(period = 'live') {
    if (!cpuChart) return;
    
    const basePath = window.basePath || '';
    fetch(`${basePath}/api/cpu?period=${period}`)
        .then(r => {
            if (!r.ok) throw new Error('Network response was not ok');
            return r.json();
        })
        .then(data => {
            if (data.error) { console.error(data.error); return; }
            const labels = data.utc_labels.map(ts => {
                const d = new Date(ts);
                if (period === 'live' ) {
                    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                } else if (period === 'hour') {
                    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
                } else if (period === 'day') {
                    return d.getHours().toString().padStart(2, '0') + ':00';
                } else {
                    return d.toLocaleDateString('ru-RU');
                }
            });

            const cpu = data.cpu_percent || [];
            const ram = data.ram_percent || [];

            cpuChart.data.labels = labels;
            cpuChart.data.datasets[0].data = cpu;
            cpuChart.data.datasets[1].data = ram;

            // Динамический цвет CPU: если последняя точка > 80% -> красная
            const latestCpu = cpu.length ? cpu[cpu.length - 1] : 0;
            const colors = themeColors();
            if (latestCpu > 80) {
                cpuChart.data.datasets[0].borderColor = 'rgba(220,20,60,1)';
                cpuChart.data.datasets[0].backgroundColor = 'rgba(220,20,60,0.12)';
            } else {
                cpuChart.data.datasets[0].borderColor = colors.cpuBorder;
                cpuChart.data.datasets[0].backgroundColor = colors.cpuFill;
            }

            cpuChart.update('none');
        })
        .catch(err => console.error('Ошибка при загрузке CPU данных:', err));

    // автообновление для live
    if (period === 'live') {
        if (cpuInterval) clearTimeout(cpuInterval);
        cpuInterval = setTimeout(() => updateCpuChart('live'), LIVE_UPDATE_MS);
    }
}

function toggleCpuChartVisibility() {
    const chartContainer = document.getElementById('cpuChartContainer');
    const toggleBtn = document.getElementById('toggleCpuChartBtn');
    if (!chartContainer || !toggleBtn) return;
    const icon = toggleBtn.querySelector('i');
    if (!icon) return;
    const isVisible = chartContainer.style.display === 'block';

    if (isVisible) {
        chartContainer.style.display = 'none';
        toggleBtn.classList.remove('active', 'btn-primary');
        toggleBtn.classList.add('btn-outline-secondary');
        toggleBtn.setAttribute('title', 'Показать график');
        icon.classList.remove('bi-graph-down');
        icon.classList.add('bi-graph-up');
        localStorage.setItem('cpuChartVisible', 'false');

        // Останавливаем автообновление при скрытии
        if (cpuInterval) {
            clearTimeout(cpuInterval);
            cpuInterval = null;
        }
        
        // Уничтожаем график при скрытии
        if (cpuChart) {
            cpuChart.destroy();
            cpuChart = null;
        }
    } else {
        chartContainer.style.display = 'block';
        toggleBtn.classList.add('active', 'btn-primary');
        toggleBtn.classList.remove('btn-outline-secondary');
        toggleBtn.setAttribute('title', 'Скрыть график');
        icon.classList.remove('bi-graph-up');
        icon.classList.add('bi-graph-down');
        localStorage.setItem('cpuChartVisible', 'true');

        setTimeout(() => {
            initCpuChart();
            // Запускаем обновление при показе
            const activePeriod = document.querySelector('.cpu-period.active');
            updateCpuChart(activePeriod ? activePeriod.dataset.period : 'live');
        }, 10);
    }
}

// Системная информация
const VPN_SVC_STATE_RU = {
    active: 'Активен',
    inactive: 'Остановлен',
    failed: 'Сбой',
    activating: 'Запуск',
    deactivating: 'Остановка',
    reloading: 'Перезагрузка',
    'not-found': 'Нет unit',
    unknown: 'Неизвестно',
};

function vpnSvcStateRu(state) {
    return VPN_SVC_STATE_RU[state] || state;
}

function formatDiskGb(n) {
    if (n == null || Number.isNaN(Number(n))) return '—';
    const x = Number(n);
    return Math.abs(x - Math.round(x)) < 1e-6 ? String(Math.round(x)) : x.toFixed(1);
}

function formatCpuPercent(p) {
    if (p == null || Number.isNaN(Number(p))) return '—';
    const x = Number(p);
    return Math.abs(x - Math.round(x)) < 0.05 ? String(Math.round(x)) : x.toFixed(1);
}

function setUtilMeter(fillEl, pct) {
    if (!fillEl) return;
    const raw = Number(pct);
    const v = Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : 0;
    fillEl.style.width = `${v}%`;
    fillEl.classList.remove('dash-meter__fill--ok', 'dash-meter__fill--warn', 'dash-meter__fill--crit');
    if (v < 50) fillEl.classList.add('dash-meter__fill--ok');
    else if (v <= 80) fillEl.classList.add('dash-meter__fill--warn');
    else fillEl.classList.add('dash-meter__fill--crit');
    const track = fillEl.closest('.dash-meter');
    if (track) track.setAttribute('aria-valuenow', String(Math.round(v)));
}

function updateBlockedVpnStat(valueEl, sepEl, hintEl, count) {
    const value = Number(count) || 0;
    if (valueEl) {
        valueEl.textContent = String(value);
        valueEl.classList.toggle('d-none', value <= 0);
    }
    if (sepEl) sepEl.classList.toggle('d-none', value <= 0);
    if (hintEl) hintEl.textContent = value > 0 ? 'онлайн / заблокировано' : 'онлайн';
}

function updateOpenvpnStat(blockedEl, blockedSepEl, expiringEl, expiringSepEl, hintEl, blockedCount, expiringCount) {
    const blocked = Number(blockedCount) || 0;
    const expiring = Number(expiringCount) || 0;
    if (blockedEl) {
        blockedEl.textContent = String(blocked);
        blockedEl.classList.toggle('d-none', blocked <= 0);
    }
    if (blockedSepEl) blockedSepEl.classList.toggle('d-none', blocked <= 0);
    if (expiringEl) {
        expiringEl.textContent = String(expiring);
        expiringEl.classList.toggle('d-none', expiring <= 0);
    }
    if (expiringSepEl) expiringSepEl.classList.toggle('d-none', expiring <= 0);
    if (hintEl) {
        const parts = ['онлайн'];
        if (blocked > 0) parts.push('заблокировано');
        if (expiring > 0) parts.push('скоро истекают');
        hintEl.textContent = parts.join(' / ');
    }
}

function vpnInactiveSummaryPhrase(count) {
    if (count <= 0) return { text: 'Активны', allActive: true };
    const n = count;
    const mod10 = n % 10;
    const mod100 = n % 100;
    let phrase;
    if (mod10 === 1 && mod100 !== 11) {
        phrase = `${n} из 6 не активен`;
    } else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) {
        phrase = `${n} из 6 не активны`;
    } else {
        phrase = `${n} из 6 не активны`;
    }
    return { text: phrase, allActive: false };
}

function updateVpnSummaryLine(services) {
    const el = document.getElementById('dash-vpn-summary');
    if (!el) return;
    if (!Array.isArray(services) || services.length === 0) {
        el.textContent = 'Нет данных о службах';
        el.classList.remove('text-success', 'text-warning');
        el.classList.add('text-muted');
        return;
    }
    const inactive = services.filter((s) => s.state !== 'active');
    const { text, allActive } = vpnInactiveSummaryPhrase(inactive.length);
    el.textContent = text;
    el.classList.toggle('text-success', allActive);
    el.classList.toggle('text-warning', !allActive);
    el.classList.remove('text-muted');
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text == null ? '' : String(text);
    return d.innerHTML;
}

function renderVpnServices(services) {
    const root = document.getElementById('dash-vpn-services-root');
    if (!root || !Array.isArray(services)) return;
    const kindLabel = (k) => (k === 'wireguard' ? 'WireGuard' : 'OpenVPN');
    root.innerHTML = services
        .map((s) => {
            const active = s.state === 'active';
            const restartBtn = active
                ? ''
                : `<div class="dash-svc__actions"><button type="button" class="btn btn-sm btn-outline-warning dash-svc__restart" data-unit="${escapeHtml(s.unit)}" title="Перезапустить службу"><i class="bi bi-arrow-clockwise" aria-hidden="true"></i><span class="visually-hidden"> Перезапуск</span></button></div>`;
            return `<div class="dash-svc" role="listitem" data-unit="${escapeHtml(s.unit)}">
        <span class="dash-svc__state" data-state="${escapeHtml(s.state)}">${escapeHtml(vpnSvcStateRu(s.state))}</span>
        <div class="dash-svc__main min-w-0">
          <div class="dash-svc__line d-flex flex-wrap align-items-baseline gap-2">
            <span class="fw-medium">${escapeHtml(s.label)}</span>
            <span class="text-muted small">${escapeHtml(kindLabel(s.kind))}</span>
          </div>
        </div>
        ${restartBtn}
      </div>`;
        })
        .join('');
}

function initDashVpnRestartClicks() {
    const root = document.getElementById('dash-vpn-services-root');
    if (!root || root.dataset.vpnRestartBound === '1') return;
    root.dataset.vpnRestartBound = '1';
    root.addEventListener('click', async (e) => {
        const btn = e.target.closest('.dash-svc__restart');
        if (!btn || btn.disabled) return;
        e.preventDefault();
        const unit = btn.getAttribute('data-unit');
        if (!unit) return;
        let basePath = window.basePath || '';
        if (!basePath) {
            const path = window.location.pathname;
            if (path.includes('/status')) basePath = '/status';
        }
        btn.disabled = true;
        try {
            const res = await fetch(`${basePath}/api/vpn-service/restart`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ unit }),
            });
            let payload = {};
            try {
                payload = await res.json();
            } catch {
                payload = {};
            }
            if (!res.ok || !payload.ok) {
                window.alert(payload.error || payload.detail || 'Не удалось перезапустить службу');
            }
            await updateSystemInfo();
        } catch (err) {
            console.error(err);
            window.alert('Ошибка сети при перезапуске службы');
        } finally {
            btn.disabled = false;
        }
    });
}

async function updateSystemInfo() {
    try {

        let basePath = window.basePath || '';
        if (!basePath) {
            const path = window.location.pathname;
            if (path.includes('/status')) {
                basePath = '/status';
            }
        }
        const response = await fetch(basePath + '/api/system_info');
        const data = await response.json();
        const memoryElement = document.getElementById('memory_used');
        const diskUsedDetail = document.getElementById('disk_used');
        const diskTotalDetail = document.getElementById('disk_total');
        const diskUsedKpi = document.getElementById('admin-kpi-disk-used');
        const diskTotalKpi = document.getElementById('admin-kpi-disk-total');
        const networkElement = document.getElementById('network_load');
        const interfaceElement = document.getElementById('network_interface');
        const rxElement = document.getElementById('rx_bytes');
        const txElement = document.getElementById('tx_bytes');
        const openvpn = data.vpn_clients?.OpenVPN ?? 0;
        const wireguard = data.vpn_clients?.WireGuard ?? 0;
        const openvpnBlocked = data.vpn_blocked?.OpenVPN ?? 0;
        const wireguardBlocked = data.vpn_blocked?.WireGuard ?? 0;
        const openvpnExpiring = data.openvpn_expiring_certs ?? 0;

        if (memoryElement && memoryElement.textContent !== String(data.memory_used)) {
            memoryElement.textContent = data.memory_used;
        }

        const du = formatDiskGb(data.disk_used);
        const dt = formatDiskGb(data.disk_total);
        if (diskUsedDetail && diskUsedDetail.textContent !== du) diskUsedDetail.textContent = du;
        if (diskTotalDetail && diskTotalDetail.textContent !== dt) diskTotalDetail.textContent = dt;
        if (diskUsedKpi && diskUsedKpi.textContent !== du) diskUsedKpi.textContent = du;
        if (diskTotalKpi && diskTotalKpi.textContent !== dt) diskTotalKpi.textContent = dt;

        if (interfaceElement && interfaceElement.textContent !== data.network_interface) interfaceElement.textContent = data.network_interface;
        const rxStr =
            typeof data.rx_bytes === 'number'
                ? data.rx_bytes.toLocaleString('ru-RU')
                : String(data.rx_bytes ?? '');
        const txStr =
            typeof data.tx_bytes === 'number'
                ? data.tx_bytes.toLocaleString('ru-RU')
                : String(data.tx_bytes ?? '');
        if (rxElement && rxElement.textContent !== rxStr) rxElement.textContent = rxStr;
        if (txElement && txElement.textContent !== txStr) txElement.textContent = txStr;

        let networkHtml = '';
        for (const [iface, stats] of Object.entries(data.network_load)) {
            networkHtml += `<p><b>${iface}</b>: Передача: ${stats.sent_speed} Мбит/с, Прием: ${stats.recv_speed} Мбит/с</p>`;
        }
        if (networkElement && networkElement.innerHTML !== networkHtml) networkElement.innerHTML = networkHtml;

        const elOvpn = document.getElementById('admin-stat-ovpn');
        const elWg = document.getElementById('admin-stat-wg');
        const elOvpnBlocked = document.getElementById('admin-stat-ovpn-blocked');
        const elWgBlocked = document.getElementById('admin-stat-wg-blocked');
        const elOvpnBlockedSep = document.getElementById('admin-stat-ovpn-blocked-sep');
        const elWgBlockedSep = document.getElementById('admin-stat-wg-blocked-sep');
        const elOvpnExpiring = document.getElementById('admin-stat-ovpn-expiring');
        const elOvpnExpiringSep = document.getElementById('admin-stat-ovpn-expiring-sep');
        const elOvpnHint = document.getElementById('admin-stat-ovpn-hint');
        const elWgHint = document.getElementById('admin-stat-wg-hint');
        const elKpiCpu = document.getElementById('admin-kpi-cpu');
        const elKpiUptime = document.getElementById('admin-kpi-uptime');
        if (elOvpn && elOvpn.textContent !== String(openvpn)) elOvpn.textContent = String(openvpn);
        if (elWg && elWg.textContent !== String(wireguard)) elWg.textContent = String(wireguard);
        updateOpenvpnStat(elOvpnBlocked, elOvpnBlockedSep, elOvpnExpiring, elOvpnExpiringSep, elOvpnHint, openvpnBlocked, openvpnExpiring);
        updateBlockedVpnStat(elWgBlocked, elWgBlockedSep, elWgHint, wireguardBlocked);
        const cpuStr = formatCpuPercent(data.cpu_load);
        if (elKpiCpu && elKpiCpu.textContent !== cpuStr) elKpiCpu.textContent = cpuStr;
        const cpuBar = document.getElementById('cpu_bar');
        const rawCpuNum = Number(data.cpu_load);
        setUtilMeter(cpuBar, Number.isFinite(rawCpuNum) ? rawCpuNum : 0);

        const elRamPct = document.getElementById('admin-kpi-ram-pct');
        const elMemUsed = document.getElementById('admin-kpi-mem-used');
        const elMemTotal = document.getElementById('admin-kpi-mem-total');
        let ramPct = data.memory_percent;
        if (ramPct == null && data.memory_total > 0) {
            ramPct = Math.round((100 * Number(data.memory_used)) / Number(data.memory_total) * 10) / 10;
        }
        const ramPctStr = ramPct == null ? '—' : formatCpuPercent(ramPct);
        if (elRamPct && elRamPct.textContent !== ramPctStr) elRamPct.textContent = ramPctStr;
        if (elMemUsed && elMemUsed.textContent !== String(data.memory_used)) elMemUsed.textContent = data.memory_used;
        if (elMemTotal && data.memory_total != null && elMemTotal.textContent !== String(data.memory_total)) {
            elMemTotal.textContent = data.memory_total;
        }
        const ramBar = document.getElementById('ram_bar');
        setUtilMeter(ramBar, ramPct == null || !Number.isFinite(Number(ramPct)) ? 0 : Number(ramPct));
        if (elKpiUptime && elKpiUptime.textContent !== data.uptime) {
            elKpiUptime.textContent = data.uptime;
            elKpiUptime.setAttribute('title', data.uptime);
        }

        const elCpuCoresKpi = document.getElementById('admin-kpi-cpu-cores');
        const nCores = data.cpu_cores;
        if (elCpuCoresKpi && nCores != null && elCpuCoresKpi.textContent !== String(nCores)) {
            elCpuCoresKpi.textContent = String(nCores);
        }

        const elHostOs = document.getElementById('dash-host-os');
        if (elHostOs && data.os_label != null && elHostOs.textContent !== String(data.os_label)) {
            elHostOs.textContent = data.os_label;
        }

        if (Array.isArray(data.vpn_services)) {
            renderVpnServices(data.vpn_services);
            updateVpnSummaryLine(data.vpn_services);
        }

    } catch (error) {
        console.error('Ошибка при загрузке данных:', error);
    }
}

// График vnstat
let selectedIface = null;
let selectedPeriod = 'day';
let bwChartInstance = null;

const ifaceDisplayNames = {
    'antizapret-udp': 'OpenVPN | Antizapret UDP ',
    'antizapret-tcp': 'OpenVPN | Antizapret TCP',
    'vpn-udp': 'OpenVPN | VPN-UDP',
    'vpn-tcp': 'OpenVPN | VPN-TCP',
    'vpn': 'WireGuard | VPN',
    'antizapret': 'WireGuard | Antizapret',
};

async function loadInterfaces() {
    try {
        const basePath = window.basePath || '';
        const res = await fetch(basePath + '/api/interfaces');
        const data = await res.json();
        const container = document.getElementById('interface-filters');
        container.innerHTML = '';

        const defaultIfaces = ['eth0', 'enp3s0', 'ens33', 'wlan0'];
        let selectedByDefault = null;

        data.interfaces.forEach(iface => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-outline-secondary iface';
            btn.dataset.iface = iface;
            btn.textContent = iface;

            btn.addEventListener('click', () => selectIface(iface, btn));

            container.appendChild(btn);

            if (!selectedByDefault && defaultIfaces.includes(iface)) {
                selectedByDefault = { iface, btn };
            }
        });

        if (!selectedByDefault && data.interfaces.length > 0) {
            selectedByDefault = { iface: data.interfaces[0], btn: container.children[0] };
        }

        if (selectedByDefault) {
            selectIface(selectedByDefault.iface, selectedByDefault.btn);
        }

    } catch (e) {
        console.error('Ошибка при загрузке интерфейсов:', e);
    }
}

function selectIface(iface, btn) {
    document.querySelectorAll('.iface').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedIface = iface;
    document.getElementById('bwIface').textContent = ifaceDisplayNames[iface] || iface;
    updateGraph();
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

async function updateGraph() {
    if (!selectedIface) return;
    const bwBox = document.getElementById('bwChartContainer');
    if (!bwBox || bwBox.style.display !== 'block') return;

    try {
        const basePath = window.basePath || '';
        const res = await fetch(`${basePath}/api/bw?iface=${selectedIface}&period=${selectedPeriod}`);
        const data = await res.json();
        if (!data) return;

        const rawLabels = (data.utc_labels && data.utc_labels.length) ? data.utc_labels : (data.labels || []);
        const xAxisTitle = (selectedPeriod === 'hour' || selectedPeriod === 'day') ? 'Время' : 'Дата';

        // Преобразование UTC меток в локальное время
        const labels = rawLabels.map(lab => {
            const d = new Date(lab);
            if (isNaN(d.getTime())) {
                console.warn('Invalid UTC label:', lab);
                return lab;
            }
            if (selectedPeriod === 'hour' || selectedPeriod === 'day') {
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            } else {
                return d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
            }
        });

        const ctx = document.getElementById("bwChart").getContext("2d");
        const colors = getThemeColors();

        const datasets = [
            {
                label: "Принято",
                data: data.rx_mbps,
                fill: true,
                borderColor: colors.rx.border,
                backgroundColor: colors.rx.fill,
                tension: 0.2,
                pointRadius: 2
            },
            {
                label: "Передано",
                data: data.tx_mbps,
                fill: true,
                borderColor: colors.tx.border,
                backgroundColor: colors.tx.fill,
                tension: 0.2,
                pointRadius: 2
            }
        ];

        if (bwChartInstance) {
            bwChartInstance.data.labels = labels;
            bwChartInstance.data.datasets = datasets;
            bwChartInstance.options.scales.x.title.text = xAxisTitle;
            bwChartInstance.options.scales.x.title.color = colors.text;
            bwChartInstance.options.scales.y.title.color = colors.text;
            bwChartInstance.options.scales.x.ticks.color = colors.text;
            bwChartInstance.options.scales.y.ticks.color = colors.text;
            bwChartInstance.options.scales.x.grid.color = colors.grid;
            bwChartInstance.options.scales.y.grid.color = colors.grid;
            bwChartInstance.options.plugins.legend.labels.color = colors.text;
            bwChartInstance.update();
        } else {
            bwChartInstance = new Chart(ctx, {
                type: "line",
                data: { labels, datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    interaction: { mode: "index", intersect: false },
                    scales: {
                        y: {
                            title: { 
                                display: true, 
                                text: "Мбит/с",
                                color: colors.text
                            },
                            beginAtZero: true,
                            grid: { color: colors.grid },
                            ticks: { color: colors.text }
                        },
                        x: {
                            title: { 
                                display: true, 
                                text: xAxisTitle,
                                color: colors.text
                            },
                            grid: { color: colors.grid },
                            ticks: { color: colors.text }
                        }
                    },
                    plugins: {
                        legend: { 
                            position: "bottom", 
                            labels: { 
                                color: colors.text,
                                usePointStyle: false 
                            } 
                        }
                    }
                }
            });
        }
    } catch (e) {
        console.error("Ошибка при обновлении графика bw:", e);
    }
}

function toggleChartVisibility() {
    const chartContainer = document.getElementById('bwChartContainer');
    const toggleChartBtn = document.getElementById('toggleChartBtn');
    if (!chartContainer || !toggleChartBtn) return;
    const icon = toggleChartBtn.querySelector('i');
    if (!icon) return;
    const isVisible = chartContainer.style.display === 'block';

    if (isVisible) {
        chartContainer.style.display = 'none';
        toggleChartBtn.classList.remove('active', 'btn-primary');
        toggleChartBtn.classList.add('btn-outline-secondary');
        toggleChartBtn.setAttribute('title', 'Показать график');
        icon.classList.remove('bi-graph-down');
        icon.classList.add('bi-graph-up');
        localStorage.setItem('chartVisible', 'false');
        
        // Уничтожаем график при скрытии
        if (bwChartInstance) {
            bwChartInstance.destroy();
            bwChartInstance = null;
        }
    } else {
        chartContainer.style.display = 'block';
        toggleChartBtn.classList.add('active', 'btn-primary');
        toggleChartBtn.classList.remove('btn-outline-secondary');
        toggleChartBtn.setAttribute('title', 'Скрыть график');
        icon.classList.remove('bi-graph-up');
        icon.classList.add('bi-graph-down');
        localStorage.setItem('chartVisible', 'true');
        
        setTimeout(() => {
            updateGraph();
        }, 10);
    }
}

// Инициализация после загрузки страницы
document.addEventListener('DOMContentLoaded', () => {
    const vpnCollapse = document.getElementById('dashVpnServicesCollapse');
    const vpnToggle = document.getElementById('dashVpnServicesToggle');
    if (vpnCollapse && vpnToggle) {
        vpnCollapse.addEventListener('shown.bs.collapse', () => {
            vpnToggle.setAttribute('aria-expanded', 'true');
        });
        vpnCollapse.addEventListener('hidden.bs.collapse', () => {
            vpnToggle.setAttribute('aria-expanded', 'false');
        });
    }

    initDashVpnRestartClicks();

    // Восстановление состояния CPU графика
    const cpuChartContainer = document.getElementById('cpuChartContainer');
    const toggleCpuChartBtn = document.getElementById('toggleCpuChartBtn');
    const cpuSavedState = localStorage.getItem('cpuChartVisible') === 'true';

    if (cpuSavedState && toggleCpuChartBtn && cpuChartContainer) {
        cpuChartContainer.style.display = 'block';
        toggleCpuChartBtn.classList.add('active', 'btn-primary');
        toggleCpuChartBtn.classList.remove('btn-outline-secondary');
        toggleCpuChartBtn.setAttribute('title', 'Скрыть график');
        const cpuIcon = toggleCpuChartBtn.querySelector('i');
        cpuIcon.classList.remove('bi-graph-up');
        cpuIcon.classList.add('bi-graph-down');
    }

    // Инициализация CPU графика только если он видим
    if (cpuChartContainer && cpuChartContainer.style.display === 'block') {
        setTimeout(() => {
            initCpuChart();
            updateCpuChart('live');
        }, 100);
    }

    // Обработчики для кнопок периода CPU
    document.querySelectorAll('.cpu-period').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.cpu-period').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            if (cpuInterval) clearTimeout(cpuInterval);
            updateCpuChart(this.dataset.period);
        });
    });

    // Обработчик для кнопки переключения видимости CPU графика
    if (toggleCpuChartBtn) {
        toggleCpuChartBtn.addEventListener('click', toggleCpuChartVisibility);
    }

    // Восстановление состояния BW графика
    const toggleChartBtn = document.getElementById('toggleChartBtn');
    if (toggleChartBtn) {
        toggleChartBtn.addEventListener('click', toggleChartVisibility);
        
        const savedState = localStorage.getItem('chartVisible') === 'true';
        const chartContainer = document.getElementById('bwChartContainer');
        const icon = toggleChartBtn.querySelector('i');
        
        if (savedState && chartContainer) {
            chartContainer.style.display = 'block';
            toggleChartBtn.classList.add('active', 'btn-primary');
            toggleChartBtn.classList.remove('btn-outline-secondary');
            toggleChartBtn.setAttribute('title', 'Скрыть график');
            icon.classList.remove('bi-graph-up');
            icon.classList.add('bi-graph-down');
            
            setTimeout(() => {
                loadInterfaces();
            }, 100);
        } else {
            // Если график скрыт, всё равно загружаем интерфейсы
            loadInterfaces();
        }
    } else {
        loadInterfaces();
    }

    // Обработчики для кнопок периода BW графика
    document.querySelectorAll('.period').forEach(b => {
        b.addEventListener('click', e => {
            document.querySelectorAll('.period').forEach(p => p.classList.remove('active'));
            e.currentTarget.classList.add('active');
            selectedPeriod = e.currentTarget.dataset.period;
            updateGraph();
        });

        if (b.dataset.period === selectedPeriod) {
            b.classList.add('active');
        }
    });

    // Обновляем стиль при переключении темы
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        const cpuChartEl = document.getElementById('cpuChartContainer');
        if (cpuChart && cpuChartEl && cpuChartEl.style.display === 'block') {
            cpuChart.destroy();
            initCpuChart();
            const active = document.querySelector('.cpu-period.active');
            updateCpuChart(active ? active.dataset.period : 'live');
        }
        
        if (bwChartInstance) {
            bwChartInstance.destroy();
            bwChartInstance = null;
            updateGraph();
        }
    });

    updateSystemInfo();
    setInterval(updateSystemInfo, 5000);
});