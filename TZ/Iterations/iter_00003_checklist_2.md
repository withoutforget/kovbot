# Итерация 00003 — Чеклист (прогон 2)

Дата: 2026-04-16

Ниже — проверка соответствия флоу из `TZ/dialogs.md` (8 схем) по факту реализации.

## 1. Главное меню и навигация

- [x] `/start` ведёт в меню: `kov/tg/handlers.py`, `kov/tg/dialogs/menu.py`
- [x] Создание/обновление профиля пользователя: `POST /users/ensure` (`kov/web/routers/users.py`) вызывается из `kov/tg/runtime.py`
- [x] Динамический список сценариев: `GET /scenarios` (`kov/web/routers/scenarios.py`) + `Select` в `kov/tg/dialogs/menu.py`
- [x] «Продолжить незавершённый сценарий»: хранение `last_scenario` через `POST /users/profile/merge` (`kov/web/routers/users.py`) + кнопка «Продолжить» в `kov/tg/dialogs/menu.py`
- [x] «Мои данные»: экспорт/очистка `kov/tg/dialogs/export.py` + API `kov/web/routers/export.py`, `kov/web/routers/*` (clear endpoints)
- [x] «Отчёты и аналитика»: список сохранённых отчётов `kov/tg/dialogs/reports.py` + API `kov/web/routers/reports.py`
- [x] «Настройки напоминаний»: внутри трекеров `kov/tg/dialogs/mood.py`, `kov/tg/dialogs/habits.py`
- [x] Настройка часового пояса: окно `MainMenuSG.timezone` в `kov/tg/dialogs/menu.py` → `POST /users/ensure`

## 2. Сценарий «Интервью»

- [x] Старт/повтор: `kov/tg/dialogs/interview.py` (кнопка «Начать / пройти заново») + `POST /scenarios/interview/start`
- [x] Последовательные шаги/прогресс: `InterviewSG.question` (`kov/tg/dialogs/interview.py`)
- [x] Сохранение каждого ответа: `POST /scenarios/interview/answer` (`kov/web/routers/scenarios.py`)
- [x] Просмотр всех ответов: `InterviewSG.review` (`kov/tg/dialogs/interview.py`)
- [x] Редактирование блока: `InterviewSG.edit_pick` → `InterviewSG.edit_answer`
- [x] Сводка + экспорт: `InterviewSG.summary` + отправка файла `interview.json`
- [x] Прервать и вернуться в меню: `on_interrupt_clicked` + запись `last_scenario`

## 3. Сценарий «Трекер настроения»

- [x] Главный экран трекера: `MoodSG.menu` (`kov/tg/dialogs/mood.py`)
- [x] Ежедневные вопросы: `MoodSG.q_score/q_notes/q_down/q_up`
- [x] Сохранение записи: `POST /mood/entry` (`kov/web/routers/mood.py`)
- [x] История: `GET /mood/history/{user_id}` + `MoodSG.history_list/history_view`
- [x] Недельная/месячная аналитика: `GET /reports/mood/weekly|monthly/{user_id}` + окна `MoodSG.weekly/monthly`
- [x] Настройки напоминаний (вкл/выкл/время): `POST /schedule` + окна `MoodSG.settings/set_time`
- [x] Пауза/возврат: выход в меню с записью `last_scenario`

## 4. Сценарий «Техники и упражнения»

- [x] Приём запроса: `TechniquesSG.ask` (`kov/tg/dialogs/techniques.py`)
- [x] Показ 2 вариантов: `POST /techniques` (`kov/web/routers/techniques.py`) + `TechniquesSG.suggestions`
- [x] Альтернатива: кнопка «Другая подборка» → повторный запрос `POST /techniques`
- [x] Пошаговое выполнение: окно `TechniquesSG.detail`
- [x] Сохранить в историю: `POST /techniques/save`
- [x] Отметить выполнение: `POST /techniques/done`

## 5. Сценарий «Диалог с ботом»

- [x] Вход/общение: `SupportChatSG.chat` (`kov/tg/dialogs/support_chat.py`)
- [x] Отправка сообщения на бэкенд: `POST /dialog/message` (`kov/web/routers/dialog.py`)
- [x] История сообщений сохраняется: `Dialog/Message` в БД (`kov/db/models.py`, `kov/web/routers/dialog.py`)
- [x] Контекст и персонализация: `kov/rag/search/service.py` (RAG + профиль из интервью)
- [x] Отдельная кнопка выхода/возврата: `В меню` + `last_scenario`

## 6. Сценарий «Диалог про отношения»

- [x] Отдельный вход из меню: `scenario_key="relationships"` (`kov/tg/dialogs/menu.py`)
- [x] Отдельная история (отличается от общего диалога): `Scenario.key="relationships"` + отдельный `Dialog` (`kov/web/routers/dialog.py`)
- [x] Отдельный профиль поиска: `search_profile="relationship_support"` (`kov/web/routers/dialog.py`)

## 7. Сценарий «Трекер привычек»

- [x] CRUD привычек: UI `kov/tg/dialogs/habits.py` + API `kov/web/routers/habits.py`
- [x] Ежедневное заполнение «сегодня»: `HabitsSG.today_pick/today_done/log_helped/log_hindered`
- [x] Сохранение логов: `POST /habits/log`
- [x] Статистика: `GET /reports/habits/weekly|monthly/{user_id}`
- [x] Настройки напоминаний: `POST /schedule` (время/вкл/выкл) из `HabitsSG.settings`

## 8. Напоминания/уведомления/аналитика/данные

- [x] Напоминания по расписанию (UTC tick, локальное сравнение по TZ): `apps/worker/main.py`, `kov/scheduler/reminders.py`
- [x] Фиксация отправки/ответа/пропуска: `UserSchedule.last_time_asked/last_time_answered/last_time_missed` + обновление в `kov/web/routers/mood.py` и `kov/web/routers/habits.py`
- [x] Сохранение отчётов и доступ к списку: `kov/web/routers/reports.py` + `kov/tg/dialogs/reports.py`
- [x] Экспорт и очистка данных: `kov/web/routers/export.py`, `kov/tg/dialogs/export.py`

