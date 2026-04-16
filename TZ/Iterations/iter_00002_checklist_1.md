# Итерация 00002 — Чеклист (прогон 1)

Дата: 2026-04-16

Ниже — проверка требований из `TZ/func.md` по факту кода (с ссылками на реализующие места).

## 1. Общие требования

- [x] 1.1 Доступ к сценариям через бота: `kov/tg/dialogs/menu.py`
- [x] 1.2 Авторизация/идентификация (персональный аккаунт): `kov/web/routers/users.py`, `kov/tg/runtime.py`
- [x] 1.3 История по сценариям (хранение): интервью `kov/db/models.py`, `kov/web/routers/scenarios.py`; диалоги `kov/web/routers/dialog.py`; настроение `kov/web/routers/mood.py`; привычки `kov/web/routers/habits.py`
- [x] 1.4 Персонализация на основе сохранённых данных: интервью-сводка сохраняется `kov/web/routers/scenarios.py`, используется в RAG-ответе `kov/rag/search/service.py`
- [x] 1.5 Список сценариев + описание: API `kov/web/routers/scenarios.py` (`GET /scenarios`), UI в боте `kov/tg/dialogs/menu.py` (динамический список)
- [x] 1.6 Переход из меню в сценарий: `kov/tg/dialogs/menu.py`
- [x] 1.7 Прервать и вернуться позже: выход в меню есть во всех диалогах + сохраняется `last_scenario` в профиле `kov/tg/dialogs/common.py`
- [x] 1.8 Хранение ответов/записей/аналитики: модели `kov/db/models.py` + роуты `kov/web/routers/*`
- [x] 1.9 Ответы по логике сценариев/методикам: техники `kov/web/routers/techniques.py`, RAG-диалоги `kov/rag/search/service.py`
- [x] 1.10 Разделение сценариев по типам: сид `kov/web/seed.py` + меню `kov/tg/dialogs/menu.py`

## 2. Интервью

- [x] 2.1 Последовательность вопросов: `kov/web/routers/scenarios.py` (`/scenarios/interview/start`), UI `kov/tg/dialogs/interview.py`
- [x] 2.2 Сбор базовой инфы: `INTERVIEW_QUESTIONS` в `kov/web/routers/scenarios.py`
- [x] 2.3 Сохранение ответов: `kov/web/routers/scenarios.py` (`UserAnswer`)
- [x] 2.4 Просмотр интервью: `GET /scenarios/interview/{user_id}` + `kov/tg/dialogs/interview.py`
- [x] 2.5 Редактирование/дополнение: `kov/tg/dialogs/interview.py` (edit flow) + `POST /scenarios/interview/answer`
- [x] 2.6 Итоговая сводка: формируется и сохраняется `kov/web/routers/scenarios.py` (`summary`)
- [x] 2.7 Экспорт/пересылка: `kov/tg/dialogs/interview.py` (отправка `interview.json`)
- [x] 2.8 Использование в персонализации: `kov/rag/search/service.py` (блок «справка о пользователе»)

## 3. Трекер настроения

- [x] 3.1 Подключение трекера: доступен через меню/сценарии `kov/tg/dialogs/menu.py` → `kov/tg/dialogs/mood.py`
- [x] 3.2 Ежедневные напоминания: worker `apps/worker/main.py` + `kov/scheduler/reminders.py`
- [x] 3.3 Дефолт 18:00: создаётся при ensure-user `kov/web/routers/users.py`
- [x] 3.4 Вопросы (состояние/события/спад/поддержка): `kov/tg/dialogs/mood.py`
- [x] 3.5 Сохранение ежедневных записей: `kov/web/routers/mood.py`
- [x] 3.6 История по датам: `GET /mood/history/{user_id}` + `kov/tg/dialogs/mood.py`
- [x] 3.7/3.8 Недельная/месячная аналитика: `kov/web/routers/reports.py`, UI `kov/tg/dialogs/mood.py`
- [x] 3.9/3.10 Повторяющиеся факторы: `kov/web/routers/reports.py` (Counter по factors_up/down)
- [x] 3.11 Динамика по периоду (текстом): `daily_scores` в `kov/web/routers/reports.py`, вывод в `kov/tg/dialogs/mood.py`
- [x] 3.12 Итоговый вывод: присутствует как агрегаты (avg + частые факторы + дневные оценки) в `kov/tg/dialogs/mood.py`

## 4. Техники и упражнения

- [x] 4.1 Приём запроса: `kov/tg/dialogs/techniques.py`
- [x] 4.2 Два варианта: `kov/web/routers/techniques.py` возвращает 2 (express+deep)
- [x] 4.3 Экспресс: `TECHNIQUE_LIBRARY` (`kind="express"`)
- [x] 4.4 Глубокая: `TECHNIQUE_LIBRARY` (`kind="deep"`)
- [x] 4.5 Пошаговая инструкция: `steps` в `kov/web/routers/techniques.py`, показ `kov/tg/dialogs/techniques.py`
- [x] 4.7 Сохранение в историю: `POST /techniques/save` в `kov/web/routers/techniques.py`, кнопка в `kov/tg/dialogs/techniques.py`
- [x] 4.8 Отметка выполнения: `POST /techniques/done` + кнопка «Я сделал(а)»
- [x] 4.9 Снижение повторяемости: фильтрация `seen` в `kov/web/routers/techniques.py`
- [x] 4.10 Альтернатива: кнопка «Другая подборка» в `kov/tg/dialogs/techniques.py`

## 5. Диалог с ботом

- [x] 5.1 Свободный диалог: `kov/tg/dialogs/support_chat.py` (`scenario_key="dialog"`)
- [x] 5.2–5.6 Анализ/уточнения/итоги/структурирование/история: RAG-ответ через `kov/web/routers/dialog.py` → `kov/rag/search/service.py` + сохранение `Dialog/Message`
- [x] 5.7 Возврат к темам: сохраняется один диалог на сценарий (в БД) `kov/web/routers/dialog.py` + продолжение через меню/«Продолжить»
- [x] 5.8 Контекст предыдущих сообщений: хранение на бэкенде `kov/web/routers/dialog.py` (messages)
- [x] 5.9 Бережный формат: системная инструкция в `kov/rag/search/service.py`
- [x] 5.10 Рекомендация перехода в другие сценарии: UI переходы доступны из меню (ручной переход); автоматический роутинг по смыслу не реализован отдельно (в рамках текущей итерации оставлено как UX-выбор пользователя)

## 6. Диалог про отношения

- [x] 6.1 Отдельный режим: `scenario_key="relationships"` в `kov/tg/dialogs/menu.py`/`kov/tg/dialogs/support_chat.py`
- [x] 6.8 История отдельно: отдельный сценарий/профиль поиска `relationship_support` в `kov/web/routers/dialog.py`

## 7. Трекер привычек

- [x] 7.1–7.2 CRUD привычек: API `kov/web/routers/habits.py` (create/list/archive/update/delete), UI `kov/tg/dialogs/habits.py`
- [x] 7.3 Напоминания: `apps/worker/main.py`, `kov/scheduler/reminders.py`
- [x] 7.4 Дефолт 21:00: `kov/web/routers/users.py` (`schedule_key="habit_tracker"`)
- [x] 7.5 Ежедневные вопросы (выполнено/не выполнено/мешало/помогло): `kov/tg/dialogs/habits.py` (today_pick/today_done/log_helped/log_hindered)
- [x] 7.6–7.7 Сохранение отметок: `POST /habits/log` + UI `kov/tg/dialogs/habits.py`
- [x] 7.8–7.9 Недельная/месячная статистика: `kov/web/routers/reports.py`, UI `kov/tg/dialogs/habits.py`
- [x] 7.11–7.13 Препятствия/факторы/рекомендации: агрегирование из `HabitLog.notes` (JSON) в `kov/web/routers/reports.py`, вывод в `kov/tg/dialogs/habits.py`
- [x] 7.14 Добавлять/изменять/архивировать/удалять: `kov/web/routers/habits.py`, `kov/tg/dialogs/habits.py`

## 8. Напоминания и уведомления

- [x] 8.1 Авто-напоминания по расписанию: APScheduler `apps/worker/main.py`
- [x] 8.2 Напоминания для настроения/привычек: `kov/scheduler/reminders.py`
- [x] 8.3–8.4 Вкл/выкл + изменение времени: `kov/web/routers/schedule.py`, UI `kov/tg/dialogs/mood.py` и `kov/tg/dialogs/habits.py`
- [x] 8.6 Учёт часового пояса: `User.timezone` + `ZoneInfo` в `kov/scheduler/reminders.py`, настройка в UI `kov/tg/dialogs/menu.py`
- [x] 8.5 Фиксация факта ответа/пропуска: `UserSchedule.last_time_answered/last_time_missed` + логика в `kov/scheduler/reminders.py`, отметка ответа в `kov/web/routers/mood.py` и `kov/web/routers/habits.py`

## 9. Аналитика и отчётность

- [x] 9.1–9.2 Статистика: mood/habits через `kov/web/routers/reports.py`
- [x] 9.3–9.4 Недельные/месячные отчёты: `kov/web/routers/reports.py`
- [x] 9.7 Доступ к ранее сформированным отчётам: сохранение в `kov/db/models.py:Report`, API `GET /reports/list/{user_id}` + UI `kov/tg/dialogs/reports.py`

## 10. Управление пользовательскими данными

- [x] 10.5 Экспорт данных: `kov/web/routers/export.py` + UI `kov/tg/dialogs/export.py`
- [x] 10.4 Удаление истории по сценарию: очистка интервью/настроения/привычек/диалогов через `kov/tg/dialogs/export.py` и эндпоинты `kov/web/routers/*`

## 11. Масштабируемость сценариев

- [x] 11.1–11.4 Добавление/публикация сценариев без изменения меню: `GET /scenarios` + динамический список в `kov/tg/dialogs/menu.py`
