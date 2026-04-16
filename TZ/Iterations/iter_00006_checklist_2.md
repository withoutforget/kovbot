# Итерация 00006 — Чеклист (прогон 2, флоу из `TZ/dialogs.md`)

Дата: 2026-04-16

Цель: пройти по 8 флоу из `TZ/dialogs.md` и подтвердить, что есть:
- вход/окна/states в `aiogram_dialog`
- переходы между окнами
- сохранение данных в API/БД
- нормальная раскладка кнопок (1 колонка) там, где списки
- streaming там, где ответ генерирует LLM

## 1. Главное меню и навигация

- [x] `/start` + описание бота + подсказка про «Меню»: `kov/tg/handlers.py`
- [x] Кнопка «Меню» снизу (reply keyboard) + команда `/menu`: `kov/tg/keyboards.py`, `kov/tg/handlers.py`
- [x] Главное меню (aiogram-dialog): `kov/tg/dialogs/menu.py` (`MainMenuSG.*`)
- [x] Список сценариев с описаниями из API: `kov/web/routers/scenarios.py` (`GET /scenarios`) + `kov/tg/dialogs/menu.py` (`scenarios_getter`)
- [x] «Продолжить» (resume): `kov/tg/dialogs/menu.py:on_continue_clicked` (берёт `last_scenario`, есть fallback на последний диалог из `/dialog/list`)
- [x] «Мои данные», «Отчёты», «Напоминания», «Часовой пояс»: `kov/tg/dialogs/menu.py`, `kov/tg/dialogs/data.py`, `kov/tg/dialogs/reports.py`

## 2. «Интервью»

- [x] Окна/стейты: `kov/tg/dialogs/states.py:InterviewSG`, `kov/tg/dialogs/interview.py`
- [x] Последовательность вопросов + сохранение каждого ответа: `kov/web/routers/scenarios.py` (`/scenarios/interview/start`, `/scenarios/interview/answer`)
- [x] Просмотр ответов + редактирование: `kov/tg/dialogs/interview.py` (review/edit flow)
- [x] Сводка + экспорт: `kov/web/routers/scenarios.py` (summary), `kov/tg/dialogs/interview.py` (экспорт JSON)

## 3. «Трекер настроения»

- [x] Окна/стейты: `kov/tg/dialogs/states.py:MoodSG`, `kov/tg/dialogs/mood.py`
- [x] Ежедневная запись (4 вопроса): `kov/tg/dialogs/mood.py` → `kov/web/routers/mood.py` (`POST /mood/entry`)
- [x] История + просмотр записи: `kov/web/routers/mood.py` (`GET /mood/history/{user_id}`), окна `history_list/history_view`
- [x] Недельная/месячная аналитика: `kov/web/routers/reports.py` + окна `weekly/monthly`
- [x] Настройки напоминаний: `kov/web/routers/schedule.py`, окна `settings/set_time`

## 4. «Техники и упражнения»

- [x] Окна/стейты: `kov/tg/dialogs/states.py:TechniquesSG`, `kov/tg/dialogs/techniques.py`
- [x] 2 варианта (express/deep) + шаги: `kov/web/routers/techniques.py`
- [x] «Другая подборка», «Сохранить», «Я сделал(а)»: `kov/tg/dialogs/techniques.py` + `POST /techniques/*`

## 5. «Диалог с ботом» (general)

- [x] Окна/стейт: `kov/tg/dialogs/states.py:SupportChatSG`, `kov/tg/dialogs/support_chat.py`
- [x] Streaming ответа: `kov/tg/dialogs/support_chat.py` читает `runtime().api.stream_text("/dialog/message/stream", ...)`
- [x] История сообщений сохраняется: `kov/web/routers/dialog.py` пишет `Message` в БД
- [x] Контекст реально используется при ответе: `kov/web/routers/dialog.py` (`_load_dialog_history` + `_build_query_with_history`)

## 6. «Отношения»

- [x] Отдельный режим/кнопка в меню: `kov/tg/dialogs/menu.py` (start `SupportChatSG.chat` с `scenario_key="relationships"`)
- [x] Отдельная история: `kov/web/routers/dialog.py` хранит отдельный `Dialog` по `scenario_id` (Scenario.key = relationships)
- [x] Streaming: тот же `/dialog/message/stream`

## 7. «Трекер привычек»

- [x] Окна/стейты: `kov/tg/dialogs/states.py:HabitsSG`, `kov/tg/dialogs/habits.py`
- [x] CRUD привычек: `kov/web/routers/habits.py`, UI `kov/tg/dialogs/habits.py`
- [x] Заполнение «сегодня» (выбор + done + helped/hindered): `kov/tg/dialogs/habits.py` → `POST /habits/log`
- [x] Недельная/месячная статистика: `kov/web/routers/reports.py`, UI `kov/tg/dialogs/habits.py`
- [x] Настройки напоминаний: `kov/web/routers/schedule.py`, окно `HabitsSG.settings`

## 8. Напоминания, уведомления, аналитика и данные

- [x] Scheduler (tick каждую минуту) + учёт timezone: `kov/scheduler/reminders.py`, старт `apps/worker/main.py`
- [x] Дефолтные расписания создаются при ensure-user: `kov/web/routers/users.py` (mood=18:00, habits=21:00)
- [x] Фиксация asked/answered/missed: `kov/db/models.py:ReminderEvent`, `kov/scheduler/reminders.py`, отметка answer в `kov/web/routers/mood.py` и `kov/web/routers/habits.py`
- [x] Мои данные (просмотр): `kov/tg/dialogs/data.py` (интервью/настроение/привычки/диалоги)
- [x] Экспорт/очистка: `kov/tg/dialogs/export.py`, `kov/web/routers/export.py`

## UX / раскладка кнопок (проблема «жуются / в одну строку»)

- [x] Списки переведены на `ScrollingGroup(width=1)`: `kov/tg/dialogs/menu.py`, `kov/tg/dialogs/mood.py`, `kov/tg/dialogs/habits.py`, `kov/tg/dialogs/techniques.py`, `kov/tg/dialogs/data.py`, `kov/tg/dialogs/reports.py`, `kov/tg/dialogs/interview.py`

