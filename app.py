from flask import Flask, render_template
from datetime import datetime
import csv
import requests

app = Flask(__name__)

# Функция для преобразования байт в удобный формат
def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

# Функция для склонения слова "клиент"
def pluralize_clients(count):
    if 11 <= count % 100 <= 19:
        return f"{count} клиентов"
    elif count % 10 == 1:
        return f"{count} клиент"
    elif 2 <= count % 10 <= 4:
        return f"{count} клиента"
    else:
        return f"{count} клиентов"

# Функция для получения внешнего IP-адреса
def get_external_ip():
    try:
        # Отправляем запрос к сервису ipify, чтобы получить внешний IP
        response = requests.get('https://api.ipify.org')
        if response.status_code == 200:
            return response.text  # Возвращаем IP-адрес
        return 'IP не найден'
    except Exception as e:
        return str(e)

# Преобразование даты
def format_date(date_string):
    return datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y [%H:%M]')

# Удаление префикса из имени клиента
def clean_client_name(name, prefix="antizapret-"):
    return name[len(prefix):] if name.startswith(prefix) else name

# Маскировка IP-адреса
def mask_ip(ip_address):
    parts = ip_address.split('.')
    return f"{parts[0]}.***.***.***" if len(parts) == 4 else ip_address

# Чтение данных из CSV и обработка
def read_csv(file_path, protocol):
    data = []
    total_received, total_sent = 0, 0
    with open(file_path, newline='') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Пропускаем заголовок
        for row in reader:
            if row[0] == 'CLIENT_LIST':
                received, sent = int(row[5]), int(row[6])
                total_received += received
                total_sent += sent
                data.append([
                    clean_client_name(row[1]), mask_ip(row[2]), row[3],
                    format_bytes(received), format_bytes(sent),
                    format_date(row[7]), protocol
                ])
    return data, total_received, total_sent

@app.route('/')
def index():
    #udp_clients, udp_received, udp_sent = read_csv('/etc/openvpn/server/logs/antizapret-udp-status.log', 'UDP')
    #tcp_clients, tcp_received, tcp_sent = read_csv('/etc/openvpn/server/logs/antizapret-tcp-status.log', 'TCP')
    
    #Для проверки
    udp_clients, udp_received, udp_sent = read_csv('antizapret-udp-status.log', 'UDP')
    tcp_clients, tcp_received, tcp_sent = read_csv('antizapret-tcp-status.log', 'TCP')

    clients = udp_clients + tcp_clients
    total_clients = len(clients)
    total_received = format_bytes(udp_received + tcp_received)
    total_sent = format_bytes(udp_sent + tcp_sent)
    server_ip = get_external_ip()

    
    return render_template('index.html', clients=clients, total_clients_str=pluralize_clients(total_clients),
                                  total_received=total_received, total_sent=total_sent, server_ip=server_ip)
@app.route('/test')
def test():
    return render_template('test.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=1234)
