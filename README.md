<h1 align="center" >StatusOpenVPN</h1>

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


# Установка и настройка 

<details>
  <summary>Версия от 15.02.2025</summary>
  
1. Исправлены ошибки в подсчёте статистики.  
1. Внесены правки в таблице WireGuard:  
   + Добавлено отображение конечной точки.  
   + Внесены правки в столбцы «Передано/Получено» для WireGuard.  
1. Внесены правки на главной странице:  
   + Изменено расположение имени сервера и IP-адреса.  
   + Внесены правки в заголовки страниц: добавлен IP-адрес.  
   + Убрано отображение интерфейса **lo** в «Сетевой загрузке».  
   + Добавлено отображение статистики по сетевому интерфейсу в зависимости от системы.  
1. Исключена функция удаления префикса из имени клиента.  
1. Чтение лога `/etc/openvpn/server/logs/antizapret-no-cipher-status.log` отключено.

</details>


## Описание

Этот проект представляет собой приложение на языке Python, разработанное с использованием фреймворка Flask. Оно предназначено для отображения статистики подключений клиентов к OpenVPN и WireGuard. 
Основная цель приложения — визуализировать информацию о подключенных клиентах и их трафике в удобном формате.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/3071b3cc-fdb5-4db8-9a77-273d2ed1ec73">
  <img src="https://github.com/user-attachments/assets/98c1c36c-91ee-4e17-8922-bc0ca8ffde8a">
</picture>

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

2. В процессе установки будет предложено изменить порт по умолчанию **[1234]**. Вы можете ввести новый порт, если хотите, или оставить его без изменений.
3. Пароль администратора будет сгенерирован ***автоматический***.
4. После завершения установки приложение будет доступно по адресу:

    ```
    http://<IP_адрес_сервера>:[порт]
    ```

## Смена пароля

Чтобы сменить пароль администратора, выполните следующий скрипт: ``change_passwd.sh``. 

````bash
(cd web && chmod +x ./scripts/change_passwd.sh && ./scripts/change_passwd.sh)
````
Скрипт автоматически сгенерирует новый пароль для администратора. Для избежания ошибок скрипт необходимо запускать из директории /root


## Обновление сервиса
Для обновления сервиса запустите следующий скрипт: ```update.sh```
````bash
bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/update.sh)"
 ````
Этот скрипт загрузит и установит последнюю версию StatusOpenVPN. В процессе обновления будет предложено изменить **[текущий порт]**. Вы можете указать новый порт или оставить прежний.


## Удаление сервиса

Для полного удаления сервиса и всех его компонентов используйте скрипт: ``uninstall.sh``:
```bash
bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/uninstall.sh)"
```

## Примечания

1. Убедитесь, что ваш сервер имеет открытый порт, на котором будет работать ваше приложение.
2. Если вы используете облачный сервер, убедитесь, что правила брандмауэра (firewall) позволяют входящие подключения на указанный порт.
3. Данные для OpenVPN считываются из файлов `*-status.log` из директории `/etc/openvpn/server/logs/`.
4. Данные для WireGuard считываются из команды: ```wg show```


## Об авторе

Этот проект был создан и поддерживается пользователем **TheMurmabis**. Для любых вопросов или предложений, пожалуйста, обращайтесь через Issues на GitHub или через личные сообщения на [форуме](https://ntc.party/t/9270/2211).

Поддержать проект можно по ссылкам ниже:

1. Партнерские ссылки:

   - [aeza.net](https://aeza.net/?ref=535845) - VPS-сервера от 4,94€/мес с оплатой в рублях. Промо-тариф на Стокгольме за 1,09€/мес.
   - [IPhoster OÜ](http://iphoster.net/pl.php?30686) - VPS-сервера от 3.95$/мес с оплатой в рублях. Иногда попадатся российские IP, что значит что YouTube будет без рекламы.
1. Ссылки для доната:
   - [cloudtips.ru](https://pay.cloudtips.ru/p/7a335447) - Сервис для приема безналичных чаевых и донатов от Т‑Банк.
