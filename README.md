<h1 align="center" >StatusOpenVPN + TelegramBot</h1>

<p align="center">
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/stargazers">
    <img src="https://img.shields.io/github/stars/TheMurmabis/StatusOpenVPN?style=flat&labelColor=d3d3d3&color=blue"/></a>
  <a href="/CHANGELOG.md">
    <img src="https://img.shields.io/github/v/tag/TheMurmabis/StatusOpenVPN?label=version&labelColor=d3d3d3"/></a>
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/releases">
    <img src="https://img.shields.io/github/release-date/TheMurmabis/StatusOpenVPN?labelColor=d3d3d3&color=blue"/></a>
  <a href="#">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&labelColor=d3d3d3"/></a>
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/commits/main/">
    <img src="https://img.shields.io/github/last-commit/TheMurmabis/StatusOpenVPN?labelColor=d3d3d3&color=blue"/></a>
</p>


<p align="center">
  <a href="#быстрый-старт">Быстрый старт</a> ·
  <a href="#установка-ssl-https"> Установка SSL</a> ·
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/wiki/TelegramBot">TelegramBot</a> ·
  <a href="/CHANGELOG.md">Changelog</a> ·
  <a href="#faq">FAQ</a> 
    
</p>

---

# Установка и настройка 

<details>
  <summary>Правка от 18.11.2026</summary>

### StatusOpenVPN

1. На главной странице:
   - Обновлён блок «Скорость · интерфейсы»:
      - скорость приёма и передачи показана в отдельных адаптивных карточках;
      - выбранные сетевые интерфейсы можно закрепить в начале списка;
      - исчезающие во время перезапуска интерфейсы больше не ломают обновление показателей;
   - В накопленном трафике добавлены общий объём, RX/TX и их процентное соотношение.
   - Добавлен центр уведомлений со счётчиком непрочитанных событий и переходом в журнал.
   - Данные о системе и сети обновляются стабильнее и без лишних повторных опросов.
2. На страницах OpenVPN и WireGuard:
    - Добавлена отложенная блокировка клиентов OpenVPN и отключение клиентов WireGuard.
    - Добавлена кнопка копирования публичной ссылки, если она включена для клиента.
3. В настройках:
    - Добавлен пункт "Группировка истории": группирует "Историю" по имени клиента.
    - Добавлен пункт "Сбор статистики": вкл/выкл фоновый сбор статистики клиентов WireGuard.
    - Для пункта "Интерфейс WARP" обновлен фильтр для скрытия всех WARP-интерфейсов.
    - Добавлен новый раздел «Публичные ссылки».
    - Публичные ссылки доступны только при настроенном домене и действующем HTTPS-сертификате.
    - Добавлены два вида ссылок:
      - временная — срок начинается после первого открытия;
      - постоянная — работает до явного отзыва или перевыпуска.
    - На публичной странице клиент видит только разрешённые ему конфигурации.
    - На странице Телеграм добавлена прямая ссылка на бота (при наличии токена).
    - Обновлены описания параметров Antizapret в `/settings/install`.
4. Служба переведена на один процесс с четырьмя потоками.
5. Обновлено оформление главной страницы, OpenVPN, WireGuard, настроек и формы входа.

### Telegram-бот

1. Настройки доступных конфигураций синхронизированы между веб-интерфейсом и ботом.
2. Из меню клиента можно получить временную или постоянную публичную ссылку.
3. При создании OpenVPN клиента добавлен выбор готового или произвольного срока.
4. Добавлен новый пункт продления сертификата OpenVPN с отображением текущего срока.
5. В меню "Клиенты бота" добавлен пункт "Рассылка" для отправки сообщений всем клиентам бота. 
6. Пункт «Заблокированные» перенесен в раздел "Запросы".
7. Улучшено надёжное сохранение настроек при одновременной работе веб-интерфейса и бота.

</details>


---


## Описание

Этот проект представляет собой приложение на языке Python, разработанное с использованием фреймворка Flask. Оно предназначено для отображения статистики подключений клиентов к OpenVPN и WireGuard. 
Основная цель приложения — визуализировать информацию о подключенных клиентах и их трафике в удобном формате.

### Внешний вид StatusOpenVPN.
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/665d567e-49a0-43b2-9f22-9e0390f0d75a">
  <img alt="image" src="https://github.com/user-attachments/assets/ed8e90a0-9a0b-444c-a0c9-3e9328e12f42" />
</picture>

### Внешний вид TelegramBot.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/c01baed5-07f5-460b-8dd7-a94b486b9c66">
  <img width="420" height="233" alt="image" src="https://github.com/user-attachments/assets/69e1d5fc-0b70-4ad2-9a27-1515bd626399" />
</picture>

Инструкция по Telegram-боту (установка, настройка и [FAQ](https://github.com/TheMurmabis/StatusOpenVPN/wiki/TelegramBot#faq)) доступна по [ссылке](https://github.com/TheMurmabis/StatusOpenVPN/wiki/TelegramBot).

### Основные функции
- Отображение статистики подключений для OpenVPN и WireGuard.
- Краткая информация о сервере (имя, IP-адрес, uptime, ОЗУ, накопитель, сеть).
- Доступ к информации о клиентских подключениях и переданном трафике.
- Безопасный доступ с использованием аутентификации и авторизации (администраторский доступ).
- CSRF-защита и шифрование паролей.
- Поддержка изменения пароля администратора.
- Телеграмм бот: 
  - Создание и удаление клиентов OpenVPN, WireGuard и AmneziaWG.
  - Получение конфигурационных файлов клиентов.
  - Просмотр списка клиентов.
  - Пересоздание конфигурационных файлов.
  - Создание резервной копии (бэкап) и отправка её в чат Telegram.
  - Перезагрузка сервера с подтверждением.
  - Уведомления о нагрузке на сервер, о перезагрузке.
  - Список админов, список онлайн клиентов.
  - Клиентская сторона: клиенты могут получить свои конфиг файлы.
  - Ограничение выдачи конфигов по типам (OpenVPN/WireGuard, VPN/Antizapret) для каждого клиента.
  - Режим доступа для "чужих": запросы на вступление, их отключение и список заблокированных ID.


## Требования

Для успешной установки необходимо, чтобы на сервере были установлены следующие компоненты:

- [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN)  *(обязательно)*.
- Python 3.10 или выше. 
- Права суперпользователя (root)


## Быстрый старт

1. Для установки/обновления сервиса выполните следующую команду:
  
    ```bash
    bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/setup.sh)"
    ```

2. В процессе установки/обновления будет предложено:
    * Изменить порт по умолчанию **[1234]**. Вы можете ввести новый порт, если хотите, или оставить его без изменений.
    * Установка Teлеграмм бота.
    * [Настройка nginx и установка ssl](#установка-ssl-https).
      
    Все ответы на запросы (кроме порта) сохраняются в файл [setup](#конфигурационный-файл-setup).
4. Пароль администратора будет сгенерирован ***автоматический***.
5. После завершения установки приложение будет доступно по адресу:


|https://<домен>/status/<br>https://<IP_адрес>:[порт]/status/<br>или<br>http://<IP_адрес>:[порт] |
|:----------------------------------------------------|


## Установка SSL (HTTPS)

Для защиты соединения, так же для публичных ссылок, нужно включить HTTPS. Есть несколько вариантов:

<details>
  <summary>1. Автоматическая настройка во время установки/обновления.</summary>


При запуске `setup.sh` или `update.sh` появится вопрос:

|Do you want to enable HTTPS? (y/N):|
|:----------------------------------------------------|

- Нажмите `y` и укажите ваш домен (например, `example.com`).  
- Скрипт автоматически установит Nginx + Certbot, проверит, что домен указывает на сервер, и настроит HTTPS.  
- После успешного выполнения доступ будет по адресу: https://<домен>/StatusOpenVPN/

    > **Примечание:** Для успешного получения сертификата нужно в Antizapret-VPN отключить резервные порты OpenVPN, т.е на запрос "Use TCP/UDP ports 80 and 443 as backup for OpenVPN connections? [y/n]:" ответить N.

</details>


<details>
  <summary>2. Ручная настройка через скрипт.</summary>

### 2. Ручная настройка через скрипт
Если вы отказались во время установки, можно включить HTTPS позже:

```bash
cd /root/web/scripts
./ssl.sh -i example.com
```

Чтобы удалить конфигурацию nginx:

```bash
./ssl.sh -r example.com
```

После удаления доступ снова будет только по HTTP: http://<IP_адрес_сервера>:[порт].

</details>

<details>
  <summary>3. Интеграция в существующую конфигурацию nginx.</summary>


#### 3.1. Доступ с префиксом /status/.

Если на одном домене размещено несколько приложений, для корректной работы данного приложения необходимо настроить отдельный префикс пути (URI) и добавить блок `location /status/`:

```nginx
location /status/ {
    proxy_pass http://127.0.0.1:<порт>;
    client_max_body_size 512m;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Script-Name /status;

    proxy_redirect off;
}
```

Пример: https://example.com/status/

#### 3.2. Доступ без префикса.

Если размещение приложения под префиксом пути не требуется и доступ должен осуществляться напрямую из корня сайта (`/`), используется следующий вариант конфигурации:

```nginx
location / {
    proxy_pass http://127.0.0.1:<порт>;
    client_max_body_size 512m;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;

    proxy_redirect off;
}
```

Пример: https://example.com/

**Примечание:**

- Замените `<порт>` на порт приложения StatusOpenVPN (по умолчанию `1234`).
- Добавляйте только один из предложенных блоков в соответствующую секцию `server {}` текущего конфигурационного файла nginx.
- После внесения изменений необходимо проверить корректность конфигурации и применить её: `sudo nginx -t && sudo systemctl reload nginx`

---

</details>

## Конфигурационный файл setup

Для упрощения обновлений приложения во время установки/обновления, в директории `/root/web/` будет создан файл `setup`, который содержит следующие параметры:

| Параметр   | Значения  | Описание|
|:-----|:-----:|:-----|
|  BOT_ENABLED   | 0 / 1   | Управление включением Telegram-бота   |
|  HTTPS_ENABLED   | 0 / 1   | Управление включением HTTPS   |
|  DOMAIN   | <домен>   | Домен для HTTPS и доступа к приложению   |
|  SERVER_URL   | <адрес>   | Полный путь к приложению   |


## FAQ

<details>
  <summary>Как удалить сервис?</summary>

Для полного удаления сервиса и всех его компонентов используйте скрипт: ``uninstall.sh``:
 

```bash
bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/uninstall.sh)"
```

</details>

<details>
  <summary>Как восстановить настройки и базы данных?</summary>

Перед началом  


</details>

<details>
  <summary>Как сменить пароль администратора?</summary>

Чтобы сменить пароль администратора, выполните следующий скрипт: ``change_passwd.sh``. 

```bash
(cd web && chmod +x ./scripts/change_passwd.sh && ./scripts/change_passwd.sh)
```
Скрипт автоматически сгенерирует новый пароль для администратора. Для избежания ошибок скрипт необходимо запускать из директории /root

</details>

<details>
  <summary>Как изменить порт сервиса?</summary>

Чтобы изменить порт на котором работает сервис, выполните следующий скрипт: ``change_port.sh``. 

```bash
 bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/change_port.sh)"
```
Скрипт проверит доступность порта, и если порт доступен то сменит. 

</details>

## Примечания

1. Убедитесь, что правила брандмауэра (firewall) позволяют входящие подключения на указанный порт.
2. Данные для OpenVPN считываются из файлов `*-status.log` или через management-сокеты в `/run/openvpn-server/`.
3. Данные для WireGuard считываются из команды: ```wg show```.
4. Публичные ссылки доступны только при настроенном домене и действующем HTTPS-сертификате.


## Об авторе

Этот проект был создан и поддерживается пользователем **TheMurmabis**. Для любых вопросов или предложений, пожалуйста, обращайтесь через [Issues](https://github.com/TheMurmabis/StatusOpenVPN/issues) на GitHub или в группе [Telegram](https://t.me/+XJwXHTmMvUk3NTli) в разделе [StatusOpenVPN](https://t.me/c/2359356550/15524).

Поддержать проект можно по ссылке ниже:
   - [cloudtips.ru](https://pay.cloudtips.ru/p/7a335447) - Сервис для приема безналичных чаевых и донатов от Т‑Банк.
