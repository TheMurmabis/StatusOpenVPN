async function updateSystemInfo() {
    try {
        const response = await fetch('/api/system_info');
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
        const vpnHtml = `<a class="text-decoration-none" href="/ovpn">&#128279; <b>OpenVPN</b></a>: ${openvpn} шт.<br>
                         <a class="text-decoration-none" href="/wg">&#128279; <b>WireGuard</b></a>: ${wireguard} шт.`;

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

setInterval(updateSystemInfo, 5000);
updateSystemInfo();

let selectedIface = null;
let selectedPeriod = 'day';
let bwChartInstance = null;

async function loadInterfaces() {
    try {
        const res = await fetch('/api/interfaces');
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
    document.getElementById('bwIface').textContent = iface;
    updateGraph();
}

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
        const res = await fetch(`/api/bw?iface=${selectedIface}&period=${selectedPeriod}`);
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
            bwChartInstance.options.scales.x.ticks.color = colors.text;
            bwChartInstance.options.scales.y.ticks.color = colors.text;
            bwChartInstance.options.scales.x.grid.color = colors.grid;
            bwChartInstance.options.scales.y.grid.color = colors.grid;
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
                            title: { display: true, text: "Мбит/с" },
                            beginAtZero: true,
                            grid: { color: colors.grid },
                            ticks: { color: colors.text }
                        },
                        x: {
                            title: { display: true, text: xAxisTitle },
                            grid: { color: colors.grid },
                            ticks: { color: colors.text }
                        }
                    },
                    plugins: {
                        legend: { position: "bottom", labels: { color: colors.text, usePointStyle: false } }
                    }
                }
            });
        }
    } catch (e) {
        console.error("Ошибка при обновлении графика bw:", e);
    }
}

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (bwChartInstance) {
        bwChartInstance.destroy();
        bwChartInstance = null;
        updateGraph();
    }
});

const chartContainer = document.getElementById('bwChartContainer');
const toggleChartBtn = document.getElementById('toggleChartBtn');
const icon = toggleChartBtn.querySelector('i');
const savedState = localStorage.getItem('chartVisible') === 'true';

if (savedState) {
    chartContainer.style.display = 'block';
    toggleChartBtn.classList.add('active', 'btn-primary');
    toggleChartBtn.classList.remove('btn-outline-secondary');
    toggleChartBtn.setAttribute('title', 'Скрыть график');
    icon.classList.remove('bi-graph-up');
    icon.classList.add('bi-graph-down');
    updateGraph();
}

toggleChartBtn.addEventListener('click', () => {
    const isVisible = chartContainer.style.display === 'block';

    if (isVisible) {
        chartContainer.style.display = 'none';
        toggleChartBtn.classList.remove('active', 'btn-primary');
        toggleChartBtn.classList.add('btn-outline-secondary');
        toggleChartBtn.setAttribute('title', 'Показать график');
        icon.classList.remove('bi-graph-down');
        icon.classList.add('bi-graph-up');
        localStorage.setItem('chartVisible', 'false');
    } else {
        chartContainer.style.display = 'block';
        toggleChartBtn.classList.add('active', 'btn-primary');
        toggleChartBtn.classList.remove('btn-outline-secondary');
        toggleChartBtn.setAttribute('title', 'Скрыть график');
        icon.classList.remove('bi-graph-up');
        icon.classList.add('bi-graph-down');
        localStorage.setItem('chartVisible', 'true');
        updateGraph();
    }
});

loadInterfaces();