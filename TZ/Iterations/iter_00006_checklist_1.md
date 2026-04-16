# Итерация 00006 — Чеклист (прогон 1, требования `TZ/func.md`)

Дата: 2026-04-16

Проверка делалась по коду + быстрый прогон API:
- `pytest`: `9 passed` (локально)
- Smoke API (curl): `users/ensure`, `users/profile/merge`, `schedule`, `mood/entry`, `mood/history`, `reports/mood/weekly`, `habits` + `habits/log`, `reports/habits/weekly`

## 1. Общие требования

- [x] 1.1 Сценарии через интерфейс бота: `kov/tg/dialogs/menu.py`, `kov/tg/handlers.py`
- [x] 1.2 Авторизация/идентификация: `kov/web/routers/users.py` (`POST /users/ensure`), `kov/tg/runtime.py`
- [x] 1.3 История по сценариям: интервью `kov/web/routers/scenarios.py` + `kov/db/models.py:UserAnswer`; диалоги `kov/web/routers/dialog.py` + `kov/db/models.py:Dialog/Message`; настроение `kov/web/routers/mood.py`; привычки `kov/web/routers/habits.py`
- [x] 1.4 Персонализация: интервью-сводка хранится `kov/db/models.py:UserProfile.interview_summary` (заполняется в `kov/web/routers/scenarios.py`), используется в RAG-ответе `kov/rag/search/service.py`
- [x] 1.5 Список сценариев + описание: `kov/web/routers/scenarios.py` (`GET /scenarios`), отображение в TG `kov/tg/dialogs/menu.py`
- [x] 1.6 Переход из меню в сценарий: `kov/tg/dialogs/menu.py`
- [x] 1.7 Прервать и вернуться: кнопки «В меню» во всех диалогах + сохранение `last_scenario` в профиле `kov/tg/dialogs/common.py`, «Продолжить» `kov/tg/dialogs/menu.py`
- [x] 1.8 Хранение ответов/отметок/аналитики: модели `kov/db/models.py`, API `kov/web/routers/*`
- [x] 1.9 Логика сценариев/методики: техники `kov/web/routers/techniques.py`, RAG-ответы `kov/rag/search/service.py`
- [x] 1.10 Разграничение сценариев по типам: сид `kov/web/seed.py` + меню `kov/tg/dialogs/menu.py`

## 2. «Интервью»

- [x] 2.1–2.2 Структурированное интервью + вопросы: `kov/web/routers/scenarios.py` (`INTERVIEW_QUESTIONS`, `/scenarios/interview/start`), UI `kov/tg/dialogs/interview.py`
- [x] 2.3 Сохранение ответов: `kov/web/routers/scenarios.py` (`/scenarios/interview/answer` → `UserAnswer`)
- [x] 2.4 Просмотр: `GET /scenarios/interview/{user_id}` + UI `kov/tg/dialogs/interview.py`
- [x] 2.5 Редактирование/дополнение: `kov/tg/dialogs/interview.py` (edit flow)
- [x] 2.6 Итоговая сводка: формируется в `kov/web/routers/scenarios.py` (`summary`) и пишется в профиль
- [x] 2.7 Экспорт: `kov/tg/dialogs/interview.py` (отправка `interview.json`)
- [x] 2.8 Использование в других сценариях: `kov/rag/search/service.py` (передача `user_profile_summary`)

## 3. «Трекер настроения»

- [x] 3.1 Подключение/доступ: `kov/tg/dialogs/mood.py`
- [x] 3.2 Напоминания: `apps/worker/main.py`, `kov/scheduler/reminders.py`
- [x] 3.3 Дефолт 18:00: `kov/web/routers/users.py` (создание `UserSchedule` при ensure)
- [x] 3.4–3.5 Вопросы + сохранение: `kov/tg/dialogs/mood.py` → `kov/web/routers/mood.py` (`POST /mood/entry`)
- [x] 3.6 История: `GET /mood/history/{user_id}` + UI `kov/tg/dialogs/mood.py`
- [x] 3.7–3.12 Неделя/месяц + факторы + динамика: `kov/web/routers/reports.py`, UI `kov/tg/dialogs/mood.py`

## 4. «Техники и упражнения»

- [x] 4.1 Запрос: `kov/tg/dialogs/techniques.py`
- [x] 4.2–4.6 2 варианта (express/deep), адаптация, шаги: `kov/web/routers/techniques.py`
- [x] 4.7–4.8 Сохранить/отметить выполнение: `POST /techniques/save`, `POST /techniques/done` + кнопки `kov/tg/dialogs/techniques.py`
- [x] 4.9 Снижение повторяемости: `seen` в `kov/web/routers/techniques.py`
- [x] 4.10 Альтернатива: кнопка «Другая подборка» `kov/tg/dialogs/techniques.py`

## 5. «Диалог с ботом»

- [x] 5.1 Свободный диалог: `kov/tg/dialogs/support_chat.py` (`scenario_key="dialog"`)
- [x] 5.2–5.6 Уточнения/структурирование/история: `kov/web/routers/dialog.py` + `kov/rag/search/service.py` + сохранение `Dialog/Message`
- [x] 5.7 Возврат к теме: хранение сообщений в БД + «Продолжить» (last_scenario / fallback) `kov/tg/dialogs/menu.py`
- [x] 5.8 Контекст предыдущих сообщений используется: `kov/web/routers/dialog.py` (`_load_dialog_history` + `_build_query_with_history`)
- [x] 5.9 Бережный формат: системная инструкция `kov/rag/search/service.py`
- [x] 5.10 Рекомендация перехода к другим сценариям: добавлено в системную инструкцию `kov/rag/search/service.py` (опциональная строка с выбором сценария)

## 6. «Отношения»

- [x] 6.1 Отдельный режим: `kov/tg/dialogs/menu.py` + `kov/tg/dialogs/support_chat.py` (`scenario_key="relationships"`)
- [x] 6.8 Отдельная история: отдельный `Dialog` по `scenario_id` + отдельный `search_profile` `relationship_support` в `kov/web/routers/dialog.py`

## 7. «Трекер привычек»

- [x] 7.1–7.2 CRUD: `kov/web/routers/habits.py`, UI `kov/tg/dialogs/habits.py`
- [x] 7.3 Напоминания: `kov/scheduler/reminders.py`
- [x] 7.4 Дефолт 21:00: `kov/web/routers/users.py` (schedule `habit_tracker`)
- [x] 7.5 Ежедневные вопросы: `kov/tg/dialogs/habits.py` (today flow)
- [x] 7.6–7.7 Сохранение отметок: `POST /habits/log` (`kov/web/routers/habits.py`)
- [x] 7.8–7.13 Статистика/динамика/факторы/рекомендации: `kov/web/routers/reports.py`, UI `kov/tg/dialogs/habits.py`
- [x] 7.14 Добавлять/изменять/архивировать/удалять: `kov/web/routers/habits.py`, UI `kov/tg/dialogs/habits.py`

## 8. Напоминания

- [x] 8.1–8.2 Авто-напоминания (mood/habits): `apps/worker/main.py`, `kov/scheduler/reminders.py`
- [x] 8.3–8.4 Вкл/выкл + время: `kov/web/routers/schedule.py`, UI `kov/tg/dialogs/mood.py` и `kov/tg/dialogs/habits.py`
- [x] 8.5 Факт ответа/пропуска: `ReminderEvent` + `last_time_answered/last_time_missed` (`kov/scheduler/reminders.py`, `kov/web/routers/mood.py`, `kov/web/routers/habits.py`)
- [x] 8.6 Часовой пояс: `User.timezone`, настройка `kov/tg/dialogs/menu.py`, учёт в `kov/scheduler/reminders.py`

## 9. Аналитика и отчёты

- [x] 9.1–9.6 Сбор статистики + закономерности: `kov/web/routers/reports.py`
- [x] 9.7 Доступ к ранее сформированным отчётам: `kov/db/models.py:Report`, API `kov/web/routers/reports.py` (`/reports/list/{user_id}`, `/reports/{id}`), UI `kov/tg/dialogs/reports.py`
- [x] 9.8 Динамика по периодам: `daily_scores` (mood) и `daily` (habits) в отчётах + вывод в TG

## 10. Управление данными

- [x] 10.1–10.3 Хранение и просмотр: `kov/tg/dialogs/data.py`, модели `kov/db/models.py`
- [x] 10.4 Удаление отдельных записей/истории: `kov/tg/dialogs/data.py` (delete entry/log) + `kov/tg/dialogs/export.py` (clear разделов) + API `kov/web/routers/*`
- [x] 10.5 Экспорт: `kov/web/routers/export.py`, UI `kov/tg/dialogs/data.py` + `kov/tg/dialogs/export.py`

## 11. Масштабируемость

- [x] 11.1–11.4 Единый механизм: список сценариев и их публикация через БД (`kov/web/routers/scenarios.py` + `kov/web/seed.py`), UI меню строится из `GET /scenarios` (`kov/tg/dialogs/menu.py`)

