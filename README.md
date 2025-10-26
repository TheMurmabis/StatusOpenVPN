<h1 align="center" >StatusOpenVPN + TelegramBot</h1>

<p align="center">
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/stargazers">
    <img src="https://img.shields.io/github/stars/TheMurmabis/StatusOpenVPN?style=flat&labelColor=d3d3d3"/></a>
  <a href="/CHANGELOG.md">
    <img src="https://img.shields.io/github/v/release/TheMurmabis/StatusOpenVPN?labelColor=d3d3d3"/></a>
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/releases">
    <img src="https://img.shields.io/github/release-date/TheMurmabis/StatusOpenVPN?labelColor=d3d3d3"/></a>
  <a href="#">
    <img src="https://img.shields.io/github/languages/top/TheMurmabis/StatusOpenVPN?labelColor=d3d3d3"/></a>
  <a href="https://github.com/TheMurmabis/StatusOpenVPN/commits/main/">
    <img src="https://img.shields.io/github/last-commit/TheMurmabis/StatusOpenVPN?labelColor=d3d3d3"/></a>
</p>

---

<details>
  <summary>Содержание</summary>
  
1. [Основные функции](#основные-функции)
2. [Требования](#требования)
3. [Установка сервиса](#шаги-установки)
4. [Смена пароля администратора](#смена-пароля)
5. [Изменение порта сервиса](#изменение-порта-сервиса)
6. [Обновление сервиса](#обновление-сервиса)
7. [Удаление сервиса](#удаление-сервиса)
8. [Установка SSL (HTTPS)](#установка-ssl-https)
9. [Настройка Telegram-бота](https://github.com/TheMurmabis/StatusOpenVPN/wiki/TelegramBot)

</details>

# Установка и настройка 


<details>
  <summary>Версия от 26.10.2025</summary>

### StatusOpenVPN

1. Главная страница:
    * Исправлено отображение времени на графике. Время отображается согласно часовому поясу клиента, а не сервера.
2. OpenVPN:
    * На странице `Статистика` добавлена сортировка.

</details>


---


## Описание

Этот проект представляет собой приложение на языке Python, разработанное с использованием фреймворка Flask. Оно предназначено для отображения статистики подключений клиентов к OpenVPN и WireGuard. 
Основная цель приложения — визуализировать информацию о подключенных клиентах и их трафике в удобном формате.

### Внешний вид StatusOpenVPN.
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/3071b3cc-fdb5-4db8-9a77-273d2ed1ec73">
  <img src="https://github.com/user-attachments/assets/98c1c36c-91ee-4e17-8922-bc0ca8ffde8a">
</picture>


### Внешний вид TelegramBot.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/072ee8de-cbc5-4e73-b90a-2d671abd2bbf">
  <img src="https://github.com/user-attachments/assets/8eff640b-f420-4503-8313-a36cfbbd088f">
</picture>

Инструкция по настройке бота доступна по [ссылке](https://github.com/TheMurmabis/StatusOpenVPN/wiki/TelegramBot).


### Основные функции
- Отображение статистики подключений для OpenVPN и WireGuard.
- Краткая информация о сервере (имя, IP-адрес, uptime, ОЗУ, накопитель, сеть).
- Доступ к информации о клиентских подключениях и переданном трафике.
- Безопасный доступ с использованием аутентификации и авторизации (администраторский доступ).
- CSRF-защита и шифрование паролей.
- Поддержка изменения пароля администратора.

## Требования

Для успешной установки необходимо, чтобы на сервере были установлены следующие компоненты:

- [AntiZapret-VPN](https://github.com/GubernievS/AntiZapret-VPN)  *(обязательно)*.
- Python 3.10 или выше. 
- Права суперпользователя (root)


## Шаги установки

1. Для установки сервиса выполните следующую команду:
  
    ```bash
    bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/setup.sh)"
    ```

2. В процессе установки будет предложено:
    * Изменить порт по умолчанию **[1234]**. Вы можете ввести новый порт, если хотите, или оставить его без изменений.
    * Установка Teлеграмм бота.
    * [Настройка nginx и установка ssl](#установка-ssl-https).
      
    Все ответы на запросы (кроме порта) сохраняются в файл [setup](#конфигурационный-файл-setup).
4. Пароль администратора будет сгенерирован ***автоматический***.
5. После завершения установки приложение будет доступно по адресу:

|https://<домен><br>или<br>http://<IP_адрес_сервера>:[порт] |
|:----------------------------------------------------|


## Смена пароля

Чтобы сменить пароль администратора, выполните следующий скрипт: ``change_passwd.sh``. 

````bash
(cd web && chmod +x ./scripts/change_passwd.sh && ./scripts/change_passwd.sh)
````
Скрипт автоматически сгенерирует новый пароль для администратора. Для избежания ошибок скрипт необходимо запускать из директории /root

## Изменение порта сервиса

Чтобы изменить порт на котором работает сервис, выполните следующий скрипт: ``change_port.sh``. 

````bash
 bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/change_port.sh)"
````
Скрипт проверит доступность порта, и если порт доступен то сменит. 

## Обновление сервиса
Для обновления сервиса запустите следующий скрипт: ```update.sh```
````bash
bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/update.sh)"
 ````
Этот скрипт загрузит и установит последнюю версию StatusOpenVPN. В процессе обновления будет предложено изменить:
1. Текущий порт, вы можете указать новый порт или оставить прежний.
2. Установка Teлеграмм бота.
3. [Настройка nginx и установка ssl](#установка-ssl-https).

Все ответы на запросы (кроме порта) сохраняются в файл [setup](#конфигурационный-файл-setup).

## Удаление сервиса

Для полного удаления сервиса и всех его компонентов используйте скрипт: ``uninstall.sh``:
```bash
bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/uninstall.sh)"
```

## Установка SSL (HTTPS)

Для защиты соединения можно включить HTTPS с помощью Let's Encrypt.  
Есть два варианта:

### 1. Автоматическая настройка во время установки/обновления
При запуске `setup.sh` или `update.sh` появится вопрос:

|Do you want to enable HTTPS? (y/N):|
|:----------------------------------------------------|

- Нажмите `y` и укажите ваш домен (например, `example.com`).  
- Скрипт автоматически установит Nginx + Certbot, проверит, что домен указывает на сервер, и настроит HTTPS.  
- После успешного выполнения доступ будет по адресу: https://<домен>

    > **Примечание:** Для успешного получения сертификата нужно в Antizapret-VPN отключить резервные порты OpenVPN, т.е на запрос "Use TCP/UDP ports 80 and 443 as backup for OpenVPN connections? [y/n]:" ответить N.

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


## Конфигурационный файл setup

Для упрощения обновлений приложения во время установки/обновления, в директории `/root/web/` будет создан файл `setup`, который содержит следующие параметры:

| Параметр   | Значения  | Описание|
|:-----|:-----:|:-----|
|  BOT_ENABLED   | 0 / 1   | Управление включением Telegram-бота   |
|  HTTPS_ENABLED   | 0 / 1   | Управление включением HTTPS   |
|  DOMAIN   | <домен>   | Домен для HTTPS и доступа к приложению   |


## Примечания

1. Убедитесь, что ваш сервер имеет открытый порт, на котором будет работать ваше приложение.
2. Если вы используете облачный сервер, убедитесь, что правила брандмауэра (firewall) позволяют входящие подключения на указанный порт.
3. Данные для OpenVPN считываются из файлов `*-status.log` из директории `/etc/openvpn/server/logs/`.
4. Данные для WireGuard считываются из команды: ```wg show```


## Об авторе

Этот проект был создан и поддерживается пользователем **TheMurmabis**. Для любых вопросов или предложений, пожалуйста, обращайтесь через Issues на GitHub или в группе [Telegram](https://t.me/c/2359356550/15524).

Поддержать проект можно по ссылке ниже:
   - [cloudtips.ru](https://pay.cloudtips.ru/p/7a335447) - Сервис для приема безналичных чаевых и донатов от Т‑Банк.
