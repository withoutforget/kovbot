Окей, соберу для тебя **единый системный документ (meta-TZ)** — который объединяет:

* сценарный слой (бот) 
* ingestion / rag scan pipeline 
* retrieval / rag search pipeline 

И добавлю архитектуру, стек, принципы реализации, dev-подход и таблицы.

---

# 📄 Общее техническое задание

## ИИ-ассистент **Kov (Ков)**

---

## 1. Общая концепция системы

**Kov** — это модульный ИИ-ассистент психологической поддержки, состоящий из:

1. Telegram-бота (интерфейс сценариев)
2. RAG-системы (знания из литературы)
3. LLM-слоя (генерация ответов)
4. backend API (FastAPI)
5. системы хранения (PostgreSQL + S3 + Qdrant)

Система должна обеспечивать:

* сценарное взаимодействие (интервью, трекеры, диалог и т.д.) 
* retrieval из корпуса психологической литературы 
* ingestion pipeline документов 
* персонализацию через историю пользователя

---

## 2. Архитектура системы

### 2.1 Высокоуровневая схема

```
Telegram (aiogram)
        ↓
Bot Layer (scenarios + dialog)
        ↓
Service Layer (use-cases, dishka DI)
        ↓
-----------------------------------
| FastAPI Backend                 |
|                                |
| 1. RAG Scan API                |
| 2. RAG Search API              |
| 3. LLM API Layer               |
-----------------------------------
        ↓
Data Layer:
- PostgreSQL
- Qdrant
- S3 (rustfs)
```

---

## 3. Технологический стек

### Backend

* **Python**
* aiogram + aiogram-dialog
* FastAPI
* Dishka

### Хранилища

* PostgreSQL
* Qdrant
* rustfs

### Инфраструктура

* Docker
* Docker Compose

### Логирование

* structlog

---

## 4. Архитектурные принципы

### 4.1 Модульность

Каждый блок независим:

* bot (ui)
* rag_scan
* rag_search
* llm_api
* scheduler
* analytics

---

### 4.2 DI через Dishka

Все сервисы должны быть инжектируемыми:

* LLM clients
* repositories
* services
* config

---

### 4.3 Конфиг через YAML

```
configs/
  example.config.yaml
  dev.yaml
  prod.yaml
```

Конфиг должен включать:

* базы
* LLM
* RAG
* лимиты
* Telegram ограничения
* scheduler

---

### 4.4 Логирование (обязательно)

**structlog ВЕЗДЕ:**

* bot
* api
* rag pipeline
* llm calls
* scheduler

---

## 5. Docker архитектура

### 5.1 Образы

#### builder

* устанавливает зависимости
* собирает wheel / бинарники

#### runner

* минимальный runtime
* **может НЕ содержать файлов**
* использует external storage (S3 / volume ссылки)

#### prod_runner

* содержит:

  * код
  * конфиги
  * нужные файлы
* готов к продакшену

---

### 5.2 docker-compose

Сервисы:

```
- bot
- api
- postgres
- qdrant
- s3 (rustfs)
- worker (rag scan / async jobs)
```

---

## 6. LLM API слой

### 6.1 Требование

**Отдельный API под каждую задачу**

Примеры:

* /llm/query-planner
* /llm/reranker
* /llm/answer-generator
* /llm/chat
* /llm/extract-entities

---

### 6.2 Поддержка провайдеров

Система должна поддерживать:

* OpenAI
* Anthropic
* Google
* DeepSeek
* Qwen
* proxyapi / openrouter

---

### 6.3 Конфигурация LLM

Для каждого вызова:

```
base_url
api_key
model

temperature
top_p
top_k
max_tokens
frequency_penalty
presence_penalty
stop_sequences
```

---

### 6.4 Multi-provider routing

* fallback
* приоритет
* A/B тесты

---

## 7. RAG слой

### 7.1 Ingestion (rag_scan)

Полный pipeline обработки PDF:

* загрузка
* OCR
* парсинг
* чанкинг
* эмбеддинги
* индекс в Qdrant 

---

### 7.2 Retrieval (rag_search)

Pipeline:

```
query → planner → multi-search → rerank → expand → answer
```



---

## 8. Telegram Bot (aiogram)

### 8.1 Сценарии

* интервью
* трекер настроения
* трекер привычек
* диалог
* отношения
* техники



---

### 8.2 Хранение

Все данные:

* диалоги
* ответы
* аналитика

→ PostgreSQL (НФ3 минимум)

---

## 9. Scheduler (напоминания)

Проверка:

```sql
SELECT user_id
FROM user_schedule
WHERE at_time < now()
  AND last_time_asked > interval '4 hours'
  AND enabled = true;
```

---

## 10. Хранение данных

### 10.1 PostgreSQL

Хранит:

* users
* dialogs
* answers
* reports
* schedules
* rag sessions

---

### 10.2 Qdrant

* чанки
* embeddings
* metadata

---

### 10.3 S3 (rustfs)

* pdf
* артефакты pipeline
* intermediate data

---

## 11. Git

Использовать стандартный:

* Python `.gitignore` (GitHub template)

---

## 12. Основные use-case системы

1. Пользователь пишет в бот
2. Бот определяет сценарий
3. При необходимости → RAG
4. RAG → Qdrant → LLM
5. Ответ → Telegram

---

# 13. Промпт для генерации БД (очень важный блок)

Вот тебе нормальный production-ready prompt:

---

Ты — архитектор баз данных уровня senior.

Нужно спроектировать PostgreSQL-схему (минимум НФ3) для системы ИИ-ассистента Kov.

Контекст системы:

* Telegram-бот с психологическими сценариями
* RAG-система (Qdrant + документы)
* LLM pipeline
* аналитика и отчёты
* напоминания пользователям

Требования:

1. Сущности:

* users
* user_profiles
* dialogs
* messages
* scenarios
* scenario_sessions
* user_answers
* mood_tracker_entries
* habit_tracker
* habit_logs
* reports
* user_schedule
* rag_requests
* rag_queries
* rag_results
* rag_contexts
* llm_calls
* documents
* chunks (metadata only, не хранить embeddings)
* audit_logs

2. Требования:

* нормализация минимум до 3NF
* все связи явно через FK
* использовать UUID как PK
* timestamps везде
* soft delete где нужно
* индексы на:

  * user_id
  * created_at
  * scenario_id
  * request_id

3. Отдельно продумать:

* хранение истории диалогов
* версионность LLM ответов
* трассировка RAG pipeline
* scheduler (напоминания)

4. Выход:

* полный SQL (CREATE TABLE)
* индексы
* связи
* краткое описание таблиц

---

## 14. Что важно не упустить (реально критично)

Вот где обычно всё ломается:

* ❌ отсутствие нормальной трассировки RAG
* ❌ LLM без конфигов → невозможно дебажить
* ❌ смешивание логики bot / rag
* ❌ отсутствие версий pipeline
* ❌ плохие метаданные чанков

---

## 15. Резюме архитектуры

Kov — это:

* **bot-first система**
* с **RAG как ядром знаний**
* с **LLM как оркестратором**
* и **PostgreSQL как источником истины**

---

Если хочешь, дальше могу:

* сделать **реальную схему БД (SQL)**
* или **структуру проекта (директории + слои)**
* или **пример docker-compose под всё это**
