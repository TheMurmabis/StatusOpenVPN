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
    const icon = toggleBtn.querySelector('i');
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
        const cpuElement = document.getElementById('cpu_load');
        const memoryElement = document.getElementById('memory_used');
        const diskElement = document.getElementById('disk_used');
        const networkElement = document.getElementById('network_load');
        const uptimeElement = document.getElementById('server_uptime');
        const interfaceElement = document.getElementById('network_interface');
        const rxElement = document.getElementById('rx_bytes');
        const txElement = document.getElementById('tx_bytes');
        const vpnClientsElement = document.getElementById('vpn_clients');
        const openvpn = data.vpn_clients?.OpenVPN ?? 0;
        const wireguard = data.vpn_clients?.WireGuard ?? 0;
        const vpnHtml = `<a class="text-decoration-none" href="${basePath}/ovpn">&#128279; <b>OpenVPN</b></a>: ${openvpn} шт.<br>
                     <a class="text-decoration-none" href="${basePath}/wg">&#128279; <b>WireGuard</b></a>: ${wireguard} шт.`;

        if (cpuElement.textContent !== data.cpu_load) cpuElement.textContent = data.cpu_load;
        if (memoryElement.textContent !== data.memory_used) memoryElement.textContent = data.memory_used;
        if (diskElement.textContent !== data.disk_used) diskElement.textContent = data.disk_used;
        if (uptimeElement.textContent !== data.uptime) uptimeElement.textContent = data.uptime;

        if (interfaceElement.textContent !== data.network_interface) interfaceElement.textContent = data.network_interface;
        if (rxElement.textContent !== data.rx_bytes.toLocaleString()) rxElement.textContent = data.rx_bytes.toLocaleString();
        if (txElement.textContent !== data.tx_bytes.toLocaleString()) txElement.textContent = data.tx_bytes.toLocaleString();

        let networkHtml = '';
        for (const [iface, stats] of Object.entries(data.network_load)) {
            networkHtml += `<p><b>${iface}</b>: Передача: ${stats.sent_speed} Мбит/с, Прием: ${stats.recv_speed} Мбит/с</p>`;
        }
        if (networkElement.innerHTML !== networkHtml) networkElement.innerHTML = networkHtml;
        if (vpnClientsElement.innerHTML !== vpnHtml) vpnClientsElement.innerHTML = vpnHtml;

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
    const icon = toggleChartBtn.querySelector('i');
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
    // Восстановление состояния CPU графика
    const cpuChartContainer = document.getElementById('cpuChartContainer');
    const toggleCpuChartBtn = document.getElementById('toggleCpuChartBtn');
    const cpuSavedState = localStorage.getItem('cpuChartVisible') === 'true';

    if (cpuSavedState && toggleCpuChartBtn) {
        cpuChartContainer.style.display = 'block';
        toggleCpuChartBtn.classList.add('active', 'btn-primary');
        toggleCpuChartBtn.classList.remove('btn-outline-secondary');
        toggleCpuChartBtn.setAttribute('title', 'Скрыть график');
        const cpuIcon = toggleCpuChartBtn.querySelector('i');
        cpuIcon.classList.remove('bi-graph-up');
        cpuIcon.classList.add('bi-graph-down');
    }

    // Инициализация CPU графика только если он видим
    if (cpuChartContainer.style.display === 'block') {

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
        
        if (savedState) {
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
        if (cpuChart && document.getElementById('cpuChartContainer').style.display === 'block') {
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