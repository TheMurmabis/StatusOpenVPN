# Установка и настройка 

<details>
  <summary>Версия от 01.11.2024</summary>
    
1. Внесены правки на главную страницу:
    + Изменен шаблон отображения.
    + Оптимизирована страница под мобильные приложения.
    + Добавлено "Время работы сервера" (uptime) в системные метрики.
2. Добавлена иконка просмотра пароля на странице входа. 
3. Исправление ошибок.

</details>



## Описание

Этот проект представляет собой приложение на языке Python, разработанное с использованием фреймворка Flask. Оно предназначено для отображения статистики подключений клиентов к OpenVPN и WireGuard. 
Основная цель приложения — визуализировать информацию о подключенных клиентах и их трафике в удобном формате.

![image](https://github.com/user-attachments/assets/b079c0ef-77be-41f1-8957-736853e206ad)

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
Для смены пароля администратора необходимо запустить скрипт ``change_passwd.sh``. <br>Будет сгенерирован новый пароль.
````bash
(cd web && chmod +x ./scripts/change_passwd.sh && ./scripts/change_passwd.sh)

````
## Обновление
Для обновления сервиса необходимо запустить скрипт ```update.sh```
````bash
bash -c "$(curl -sL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/update.sh)"
 ````

## Удаление сервиса

Для удаления сервиса и всех его компонентов запустите скрипт удаления ``uninstall.sh``:
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

Этот проект был создан и поддерживается пользователем **TheMurmabis**. Для любых вопросов или предложений, пожалуйста, обращайтесь через Issues на GitHub или через личные сообщения на [форуме](https://ntc.party/u/themurmabis/activity) .
