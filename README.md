# Установка и настройка 

<details>
  <summary>Версия от 09.11.2024</summary>
    
   + Добавлен чекбокс для отображения/скрытия реального IP-адреса.

</details>



## Описание

Этот проект представляет собой приложение на языке Python, разработанное с использованием фреймворка Flask. Оно предназначено для отображения статистики подключений клиентов к OpenVPN и WireGuard. 
Основная цель приложения — визуализировать информацию о подключенных клиентах и их трафике в удобном формате.

![image](https://github.com/user-attachments/assets/2e921d58-ea0b-4b20-b19a-c53bcc51e563)


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
Скрипт автоматически сгенерирует новый пароль для администратора.


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
3. Данные для OpenVPN считываются из следующих файлов:

    + `antizapret-udp-status.log` *(обязательно)*
    + `antizapret-tcp-status.log` *(обязательно)*
    + `vpn-udp-status.log` *(необязательно)*
    + `vpn-tcp-status.log` *(необязательно)*

> **Примечание:** Файлы `antizapret-*` являются обязательными для корректного отображения данных, а файлы `vpn-*` используются при наличии.

4. Данные для WireGuard считываются из команды: ```wg show```


## Об авторе

Этот проект был создан и поддерживается пользователем **TheMurmabis**. Для любых вопросов или предложений, пожалуйста, обращайтесь через Issues на GitHub или через личные сообщения на [форуме](https://ntc.party/u/themurmabis/activity).
