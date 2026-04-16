# Итерация 00004 — Повторная проверка `TZ/func.md`

Дата: 2026-04-16

Ниже — повторная сверка требований из `TZ/func.md` по факту кода (после правок по данным/удалению/миграциям).

## 1. Общие требования

- [x] 1.1 Доступ к сценариям через бот: `kov/tg/dialogs/menu.py:1`
- [x] 1.2 Идентификация пользователя: `kov/web/routers/users.py:1`, `kov/tg/runtime.py:1`
- [x] 1.3 История по сценариям: интервью `kov/web/routers/scenarios.py:1`; настроение `kov/web/routers/mood.py:1`; привычки `kov/web/routers/habits.py:1`; диалоги `kov/web/routers/dialog.py:1`
- [x] 1.4 Персонализация: interview summary сохраняется `kov/web/routers/scenarios.py:1` и используется `kov/rag/search/service.py:1`
- [x] 1.5 Список сценариев+описание: `GET /scenarios` в `kov/web/routers/scenarios.py:1`, UI `kov/tg/dialogs/menu.py:1`
- [x] 1.6 Переход меню→сценарий: `kov/tg/dialogs/menu.py:1`
- [x] 1.7 Прерывание+возврат: в UI кнопки выхода, плюс `last_scenario` в профиле `kov/web/routers/users.py:1` + запись из `kov/tg/dialogs/menu.py:1` и диалогов
- [x] 1.8 Хранение ответов/записей/аналитики: модели `kov/db/models.py:1`, роуты `kov/web/routers/*:1`
- [x] 1.9 Логика сценариев/методик: техники `kov/web/routers/techniques.py:1`; диалог/отношения через RAG `kov/rag/search/service.py:1`
- [x] 1.10 Разграничение сценариев: `kov/web/seed.py:1`, UI `kov/tg/dialogs/menu.py:1`

## 2. Интервью

- [x] 2.1–2.2 Вопросы/последовательность: `kov/web/routers/scenarios.py:1` + UI `kov/tg/dialogs/interview.py:1`
- [x] 2.3 Сохранение: `UserAnswer` в `kov/web/routers/scenarios.py:1`
- [x] 2.4 Просмотр: `GET /scenarios/interview/{user_id}` + UI `kov/tg/dialogs/interview.py:1`
- [x] 2.5 Редактирование: edit flow `kov/tg/dialogs/interview.py:1`
- [x] 2.6 Сводка: `summary` в `kov/web/routers/scenarios.py:1`
- [x] 2.7 Экспорт: JSON в `kov/tg/dialogs/interview.py:1`
- [x] 2.8 Использование в других сценариях: `kov/rag/search/service.py:1`

## 3. Трекер настроения

- [x] 3.2–3.3 Напоминания + дефолт 18:00: `kov/web/routers/users.py:1`, `apps/worker/main.py:1`, `kov/scheduler/reminders.py:1`
- [x] 3.4–3.6 Заполнение/сохранение/история: `kov/tg/dialogs/mood.py:1`, `kov/web/routers/mood.py:1`
- [x] 3.7–3.12 Аналитика/факторы/динамика/итоги: `kov/web/routers/reports.py:1`, UI `kov/tg/dialogs/mood.py:1`

## 4. Техники и упражнения

- [x] 4.1 Приём запроса: `kov/tg/dialogs/techniques.py:1`
- [x] 4.2 Два варианта: `kov/web/routers/techniques.py:1`
- [x] 4.3–4.5 Экспресс+глубокая+шаги: `TECHNIQUE_LIBRARY` и вывод в UI
- [x] 4.6 Адаптация под запрос: keyword scoring `kov/web/routers/techniques.py:1`
- [x] 4.7–4.10 История/выполнение/снижение повторяемости/альтернатива: `kov/web/routers/techniques.py:1`, UI `kov/tg/dialogs/techniques.py:1`

## 5–6. Диалог и отношения

- [x] 5.x/6.x Режимы, история, контекст: `kov/web/routers/dialog.py:1`, `kov/tg/dialogs/support_chat.py:1`
- [x] Отдельный режим отношений: `scenario_key="relationships"` + `search_profile="relationship_support"`

## 7. Трекер привычек

- [x] 7.1–7.2 CRUD привычек: `kov/web/routers/habits.py:1`, UI `kov/tg/dialogs/habits.py:1`
- [x] 7.3–7.4 Напоминания + дефолт 21:00: `kov/web/routers/users.py:1`, `kov/scheduler/reminders.py:1`
- [x] 7.5–7.7 Ежедневные вопросы + отметки: `kov/tg/dialogs/habits.py:1`, `POST /habits/log`
- [x] 7.8–7.13 Статистика/препятствия/факторы/рекомендации: `kov/web/routers/reports.py:1`, UI `kov/tg/dialogs/habits.py:1`
- [x] 7.10 Динамика: `daily` по каждой привычке в `kov/web/routers/reports.py:1`

## 8. Напоминания и уведомления

- [x] 8.1–8.2 Авто-напоминания: `apps/worker/main.py:1`, `kov/scheduler/reminders.py:1`
- [x] 8.3–8.4 Вкл/выкл и время: `kov/web/routers/schedule.py:1`, UI `kov/tg/dialogs/mood.py:1`, `kov/tg/dialogs/habits.py:1`
- [x] 8.5 Факт ответа/пропуска: `ReminderEvent` (`kov/db/models.py:1`) + обновления `kov/scheduler/reminders.py:1`, `kov/web/routers/mood.py:1`, `kov/web/routers/habits.py:1`
- [x] 8.6 Учёт TZ: `User.timezone` + `ZoneInfo` scheduler, настройка в `kov/tg/dialogs/menu.py:1`

## 9. Аналитика и отчётность

- [x] 9.1–9.6 статистика/выводы: `kov/web/routers/reports.py:1`
- [x] 9.7 просмотр ранее сформированных отчётов: `kov/tg/dialogs/reports.py:1`

## 10. Управление данными

- [x] 10.3 Просмотр сохранённых записей: UI `kov/tg/dialogs/data.py:1`
- [x] 10.4 Удаление отдельной записи: mood delete `kov/web/routers/mood.py:1` + UI `kov/tg/dialogs/data.py:1`; habit log delete `kov/web/routers/habits.py:1` + UI `kov/tg/dialogs/data.py:1`; очистки разделов `kov/tg/dialogs/export.py:1`
- [x] 10.5 Экспорт: `kov/web/routers/export.py:1` + UI `kov/tg/dialogs/data.py:1`

## 11. Масштабируемость сценариев

- [x] 11.1–11.4 динамический список сценариев в меню: `kov/tg/dialogs/menu.py:1` + `kov/web/routers/scenarios.py:1`

