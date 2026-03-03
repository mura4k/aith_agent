# AITH Agent: Ваш университетский помощник по курсам по выбору
Интеллектуальный Telegram-бот на базе Gemini, предназначенный для автоматизации процесса выбора учебных дисциплин. Бот анализирует таблицы выборности, верифицирует данные пользователя и помогает составить индивидуальное расписание.

## Основные функции
* Персонализация: Уникальные сессии для каждого пользователя.
* Интеграция с Google Sheets: Парсинг таблиц курсов и запись результатов выбора.
* Интеллектуальный поиск: Извлечение ссылок, имен преподавателей и описаний курсов из документов (Google Docs/Notion).
* Рекомендательная система: Подбор курсов на основе запросов пользователя.
* Контроль лимитов: Автоматический подсчет зачетных единиц (ЗЕ) с учетом обязательных предметов.

## Технологический стек
LLM Engine: Gemini API

Framework: aiogram (Telegram Bot API)

External APIs: Google Sheets API

+ Google Calendar integration

## Визуализация агента
```mermaid
graph TD
    User((Пользователь)) <--> TG[Telegram Bot API]
    subgraph "AITH Agent (Python App)"
        Logic[Логика Агента / Session Manager]
        LLM[Gemini]
        Parser[Sheet Parser]
    end
    subgraph "External Data"
        GSheet[(Google Sheets: Таблица выборности)]
        GDocs[(Google Docs / Notion: Описания)]
    end

    TG <--> Logic
    Logic <--> LLM
    Logic <--> Parser
    Parser <--> GSheet
    Parser <--> GDocs
```

## Юзерский путь
```mermaid
stateDiagram-v2
    [*] --> Identification: Старт / Приветствие
    Identification --> LinkProcessing: Пересылка сообщения со ссылкой
    LinkProcessing --> Verification: Подтверждение ссылки
    Verification --> UserValidation: Ввод имени/табельного номера
    UserValidation --> CourseSelection: Анализ доступных курсов и ЗЕ
    CourseSelection --> Consultation: Вопросы по курсам/преподавателям
    Consultation --> CourseSelection: Рекомендации
    CourseSelection --> Finalizing: Набор достаточного кол-ва ЗЕ
    Finalizing --> Confirmation: Заполнение Google Таблицы
    Confirmation --> [*]: Выдача ссылки на календарь
```

