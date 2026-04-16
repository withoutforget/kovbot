# Итерация 00005 — Повторная проверка `TZ/dialogs.md`

Дата: 2026-04-16

Ниже — сверка 8 флоу из `TZ/dialogs.md` по факту реализации.

## 1) Главное меню и навигация

- [x] `/start` → меню: `kov/tg/handlers.py:1`, `kov/tg/dialogs/menu.py:1`
- [x] Сценарии (карточки: title+description): `GET /scenarios` (`kov/web/routers/scenarios.py:1`) + `Select` (`kov/tg/dialogs/menu.py:1`)
- [x] Продолжить: `last_scenario` в `UserProfile.data` (`kov/web/routers/users.py:1`) + кнопка `Продолжить` (`kov/tg/dialogs/menu.py:1`)
- [x] Мои данные: просмотр/удаление/экспорт: `kov/tg/dialogs/data.py:1`
- [x] Отчёты: список/просмотр: `kov/tg/dialogs/reports.py:1`
- [x] Настройки напоминаний: внутри трекеров: `kov/tg/dialogs/mood.py:1`, `kov/tg/dialogs/habits.py:1`

## 2) Интервью

- [x] Создание/повтор/просмотр: `kov/tg/dialogs/interview.py:1`
- [x] Редактирование блоков: `InterviewSG.edit_pick/edit_answer`
- [x] Сводка+экспорт: `InterviewSG.summary` + JSON

## 3) Трекер настроения

- [x] Заполнение за сегодня: `kov/tg/dialogs/mood.py:1` → `POST /mood/entry` (`kov/web/routers/mood.py:1`)
- [x] История по датам: `GET /mood/history/{user_id}` + окно истории
- [x] Недельная/месячная аналитика: `GET /reports/mood/*` (`kov/web/routers/reports.py:1`)
- [x] Настройки напоминаний: `POST /schedule` + `GET /schedule/{user_id}`

## 4) Техники и упражнения

- [x] Запрос → 2 предложения: `POST /techniques` (`kov/web/routers/techniques.py:1`) + UI `kov/tg/dialogs/techniques.py:1`
- [x] Альтернатива + снижение повторяемости: `seen` в API + кнопка «Другая подборка»
- [x] Сохранить/выполнено: `POST /techniques/save`, `POST /techniques/done`

## 5) Диалог с ботом

- [x] Свободный чат: `kov/tg/dialogs/support_chat.py:1`
- [x] Стриминг ответа: `POST /dialog/message/stream` (`kov/web/routers/dialog.py:1`) + draft streaming в TG
- [x] Сохранение истории: `Dialog/Message` (`kov/db/models.py:1`)

## 6) Отношения

- [x] Отдельный режим: `scenario_key="relationships"` + отдельная история (`Scenario.key="relationships"`)

## 7) Трекер привычек

- [x] CRUD привычек: `kov/tg/dialogs/habits.py:1` + `kov/web/routers/habits.py:1`
- [x] Заполнение сегодня: pick/done/helped/hindered → `POST /habits/log`
- [x] Статистика: `GET /reports/habits/*` (включая `daily` динамику)

## 8) Напоминания/уведомления/аналитика/данные

- [x] Отправка по расписанию: `apps/worker/main.py:1`, `kov/scheduler/reminders.py:1`
- [x] asked/answered/missed: `ReminderEvent` (`kov/db/models.py:1`) + обновления в scheduler и при сохранении записей
- [x] Экспорт и удаление записей: `kov/tg/dialogs/data.py:1`, `kov/tg/dialogs/export.py:1`

