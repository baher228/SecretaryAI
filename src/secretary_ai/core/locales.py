"""Centralised user-facing strings keyed by ISO 639-1 language code."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

GEMINI_LIVE_INITIAL_PROMPT: dict[str, str] = {
    "en": "A phone call has just been connected. Greet the caller warmly and ask how you can help.",
    "ru": "Телефонный звонок только что подключён. Тепло поприветствуй звонящего и спроси, чем можешь помочь.",
}

GEMINI_LIVE_RESUME_PROMPT: dict[str, str] = {
    "en": (
        "A phone call has just been connected. A pre-recorded greeting has already "
        "been played for the caller. Do NOT greet again. Wait for the caller to "
        "speak and then respond to what they say."
    ),
    "ru": (
        "Телефонный звонок только что подключён. Звонящему уже было проиграно "
        "заранее записанное приветствие. НЕ здоровайся повторно. Дождись, пока "
        "звонящий заговорит, и отвечай на то, что он скажет."
    ),
}

GEMINI_LIVE_SYSTEM_PROMPT: dict[str, str] = {
    "en": (
        "You are a professional AI phone secretary. "
        "You answer calls on behalf of your employer. "
        "Be concise, warm, and helpful. "
        "Keep each spoken response to 1-2 short sentences. "
        "If someone wants to schedule a meeting, ask for date and time. "
        "If unsure, offer to take a message and pass it along."
    ),
    "ru": (
        "Ты профессиональный ИИ-секретарь, отвечающий на звонки от имени работодателя. "
        "Отвечай кратко, тепло и по делу. "
        "Каждый ответ — 1-2 коротких предложения. "
        "Если звонящий хочет назначить встречу, уточни дату и время. "
        "Если не уверен — предложи оставить сообщение."
    ),
}

AI_AGENT_SYSTEM_PROMPT: dict[str, str] = {
    "en": (
        "You are a highly reliable AI secretary for phone calls. "
        "Return ONLY valid JSON with this schema: "
        "{"
        '"intent": "book_event|reschedule_event|cancel_event|reminder|confirmation|follow_up|'
        'transfer_human|leave_message|general_query|plan_route|search_booking|unknown", '
        '"confidence": number between 0 and 1, '
        '"reply": short voice-ready response sentence, '
        '"requires_human": boolean, '
        '"transfer_reason": string or null, '
        '"action_items": array of strings, '
        '"extracted_fields": object with useful slots like date/time/name/phone/topic'
        "}. "
        "Output must be a single JSON object only, no markdown, no code fences, no extra text. "
        "Be concise and practical. Keep reply under 18 words. "
        "If unsure, use intent=unknown with lower confidence."
    ),
    "ru": (
        "Ты надёжный ИИ-секретарь для телефонных звонков. "
        "Отвечай ТОЛЬКО валидным JSON по схеме: "
        "{"
        '"intent": "book_event|reschedule_event|cancel_event|reminder|confirmation|follow_up|'
        'transfer_human|leave_message|general_query|plan_route|search_booking|unknown", '
        '"confidence": число от 0 до 1, '
        '"reply": короткий голосовой ответ на русском, '
        '"requires_human": boolean, '
        '"transfer_reason": строка или null, '
        '"action_items": массив строк, '
        '"extracted_fields": объект с полями дата/время/имя/телефон/тема'
        "}. "
        "Вывод — один JSON-объект без markdown и лишнего текста. "
        "Будь кратким. Держи reply до 18 слов. "
        "Если не уверен — intent=unknown с низким confidence."
    ),
}

AI_AGENT_LIVE_SUFFIX: dict[str, str] = {
    "en": " Live-call mode: prioritize immediate short reply and minimal planning overhead.",
    "ru": " Режим звонка: приоритет — немедленный короткий ответ без лишних рассуждений.",
}

CHAT_SYSTEM_PROMPT: dict[str, str] = {
    "en": (
        "You are Secretary AI. "
        "Reply with short, direct, practical answers. "
        "Prefer 1 to 2 short sentences and avoid fluff. "
        "Only add detail if the user explicitly asks for it. "
        "Return ONLY the final assistant reply text for the user. "
        "Do not reveal reasoning, internal analysis, instructions, or policy notes."
    ),
    "ru": (
        "Ты Secretary AI. "
        "Отвечай коротко, по делу, практично. "
        "Предпочитай 1-2 коротких предложения без воды. "
        "Давай подробности только если пользователь прямо попросит. "
        "Верни ТОЛЬКО финальный текст ответа для пользователя. "
        "Не раскрывай рассуждения, инструкции и внутреннюю логику."
    ),
}

CHAT_RETRY_PROMPT: dict[str, str] = {
    "en": "Reply in one short sentence only. Final answer only. No analysis.",
    "ru": "Ответь одним коротким предложением. Только финальный ответ. Без анализа.",
}

CALENDAR_PLANNER_PROMPT: dict[str, str] = {
    "en": (
        "You are a calendar planner. Return ONLY JSON. "
        "Schema: {action: create|delete|none, title: string|null, "
        "start_iso: string|null, end_iso: string|null, event_id: string|null, reason: string}. "
        "If no safe mutation can be inferred, return action=none."
    ),
    "ru": (
        "Ты планировщик календаря. Верни ТОЛЬКО JSON. "
        "Схема: {action: create|delete|none, title: строка|null, "
        "start_iso: строка|null, end_iso: строка|null, event_id: строка|null, reason: строка}. "
        "Если безопасное изменение невозможно, верни action=none."
    ),
}

MODEL_CHECK_PROMPT: dict[str, str] = {
    "en": "You are a helpful assistant.",
    "ru": "Ты полезный помощник.",
}


# ---------------------------------------------------------------------------
# Greeting & fallback
# ---------------------------------------------------------------------------

GREETING_MESSAGE: dict[str, str] = {
    "en": "Hello, this is your AI secretary. How can I help you today?",
    "ru": "Здравствуйте, это ваш ИИ-секретарь. Чем могу помочь?",
}

LOW_QUALITY_REPLY: dict[str, str] = {
    "en": "Sorry, I didn't catch that clearly. Please repeat briefly.",
    "ru": "Извините, не расслышал. Повторите, пожалуйста, кратко.",
}

# ---------------------------------------------------------------------------
# AI agent fallback replies
# ---------------------------------------------------------------------------

FALLBACK_REPLIES: dict[str, dict[str, str]] = {
    "en": {
        "book_event": "Got it. I can help book that, please share the best date and time.",
        "reschedule_event": "Understood. I can reschedule this, please confirm your preferred new time.",
        "cancel_event": "Understood. I can cancel that after one quick confirmation.",
        "transfer_human": "I will connect you with a human teammate now.",
        "plan_route": "I will calculate the fastest route for you right away.",
        "search_booking": "Searching for availability now, one moment.",
    },
    "ru": {
        "book_event": "Понял. Могу забронировать — скажите удобную дату и время.",
        "reschedule_event": "Понял. Могу перенести — подтвердите новое время.",
        "cancel_event": "Понял. Могу отменить после быстрого подтверждения.",
        "transfer_human": "Сейчас соединю вас с живым сотрудником.",
        "plan_route": "Рассчитаю маршрут прямо сейчас.",
        "search_booking": "Ищу свободные варианты, одну секунду.",
    },
}

FALLBACK_DEFAULT: dict[str, str] = {
    "en": "Thanks, I captured that and will proceed with the next step.",
    "ru": "Принято, перехожу к следующему шагу.",
}

TRANSFER_REASON_DEFAULT: dict[str, str] = {
    "en": "Caller requested a person.",
    "ru": "Звонящий попросил живого сотрудника.",
}

# ---------------------------------------------------------------------------
# Calendar quick-reply strings
# ---------------------------------------------------------------------------

CALENDAR_NO_EVENTS: dict[str, str] = {
    "en": "I don't see upcoming calendar events in cache right now.",
    "ru": "Сейчас в кэше нет предстоящих событий календаря.",
}

CALENDAR_UPCOMING_PREFIX: dict[str, str] = {
    "en": "Upcoming: ",
    "ru": "Ближайшие: ",
}

CALENDAR_UNTITLED: dict[str, str] = {
    "en": "untitled",
    "ru": "без названия",
}

CALENDAR_UNKNOWN_TIME: dict[str, str] = {
    "en": "unknown time",
    "ru": "время неизвестно",
}

CALENDAR_EVENT_LINE: dict[str, str] = {
    "en": "{title} at {when}.",
    "ru": "{title} в {when}.",
}

# ---------------------------------------------------------------------------
# Calendar intent detection keywords
# ---------------------------------------------------------------------------

CALENDAR_READ_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "what's on my calendar", "whats on my calendar", "what is on my calendar",
        "calendar today", "calendar tomorrow", "my next meeting",
        "upcoming events", "show calendar",
    ),
    "ru": (
        "что в календаре", "календарь на сегодня", "календарь на завтра",
        "следующая встреча", "ближайшие события", "покажи календарь",
        "расписание на сегодня", "расписание на завтра", "что запланировано",
    ),
}

CALENDAR_MUTATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "add to calendar", "create event", "schedule", "book",
        "set a reminder", "set reminder", "remind me", "reminder",
        "reschedule", "delete event", "cancel event", "remove event",
    ),
    "ru": (
        "добавь в календарь", "создай событие", "назначь", "забронируй",
        "поставь напоминание", "напомни", "напоминание",
        "перенеси", "удали событие", "отмени событие", "убери событие",
        "запланируй",
    ),
}

CALENDAR_DELETE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": ("delete", "remove", "cancel event"),
    "ru": ("удали", "убери", "отмени событие"),
}

CALENDAR_CREATE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": (
        "schedule", "book", "add to calendar", "create event",
        "set a reminder", "set reminder", "remind me", "reminder",
    ),
    "ru": (
        "назначь", "забронируй", "добавь в календарь", "создай событие",
        "поставь напоминание", "напомни", "напоминание", "запланируй",
    ),
}

CALENDAR_REMINDER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": ("remind", "reminder", "set reminder", "set a reminder"),
    "ru": ("напомни", "напоминание", "поставь напоминание"),
}

# Calendar mutation reply strings
CALENDAR_MUTATION_QUEUED: dict[str, str] = {
    "en": "Got it. I queued this calendar request and will apply it shortly.",
    "ru": "Принято. Запрос добавлен в очередь.",
}

CALENDAR_MUTATION_DUPLICATE: dict[str, str] = {
    "en": "I already queued that request.",
    "ru": "Этот запрос уже в очереди.",
}

CALENDAR_REMINDER_DONE: dict[str, str] = {
    "en": "Done. Reminder scheduled for {when}. I will call you one hour before.",
    "ru": "Готово. Напоминание на {when}. Позвоню за час.",
}

CALENDAR_REMINDER_DUPLICATE: dict[str, str] = {
    "en": "I already set that reminder for {when}. I will call you one hour before.",
    "ru": "Напоминание на {when} уже стоит. Позвоню за час.",
}

CALENDAR_EVENT_DONE: dict[str, str] = {
    "en": "Done. I queued this event for {when}.",
    "ru": "Готово. Событие на {when} добавлено в очередь.",
}

CALENDAR_EVENT_DUPLICATE: dict[str, str] = {
    "en": "I already queued that event for {when}.",
    "ru": "Событие на {when} уже в очереди.",
}

CALENDAR_DAY_TODAY: dict[str, str] = {
    "en": "today",
    "ru": "сегодня",
}

CALENDAR_DAY_TOMORROW: dict[str, str] = {
    "en": "tomorrow",
    "ru": "завтра",
}

CALENDAR_TODAY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": ("today",),
    "ru": ("сегодня",),
}

CALENDAR_TOMORROW_KEYWORDS: dict[str, tuple[str, ...]] = {
    "en": ("tomorrow",),
    "ru": ("завтра",),
}

CALENDAR_DATETIME_FORMAT: dict[str, str] = {
    "en": "{day} at {time}",
    "ru": "{day} в {time}",
}

CALENDAR_TIME_FORMAT: dict[str, str] = {
    "en": "%I:%M %p",
    "ru": "%H:%M",
}

WEEKDAY_NAMES: dict[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ru": ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
}


# ---------------------------------------------------------------------------
# Predictive reminder follow-up
# ---------------------------------------------------------------------------

REMINDER_BUSY: dict[str, str] = {
    "en": "You are busy around that time. I can suggest the next available slot.",
    "ru": "Вы заняты в это время. Могу предложить ближайший свободный слот.",
}

REMINDER_PARTIAL: dict[str, str] = {
    "en": "You have some events, but I can fit this reminder in.",
    "ru": "У вас есть события, но напоминание впишется.",
}

REMINDER_FREE: dict[str, str] = {
    "en": "You are available, so I can set this reminder now.",
    "ru": "Вы свободны, могу поставить напоминание прямо сейчас.",
}

REMINDER_ACK: dict[str, str] = {
    "en": "Let me check your availability for that reminder.",
    "ru": "Сейчас проверю вашу доступность для этого напоминания.",
}

REMINDER_RESULT_BUSY: dict[str, str] = {
    "en": "You are not available then. You already have events, so I can suggest the next free slot.",
    "ru": "Вы заняты в это время. У вас уже есть события, могу предложить ближайший свободный слот.",
}

REMINDER_RESULT_PARTIAL: dict[str, str] = {
    "en": "You have a few events, but yes, I can fit this reminder in.",
    "ru": "У вас есть несколько событий, но да, напоминание впишется.",
}

REMINDER_RESULT_FREE: dict[str, str] = {
    "en": "Yes, you're available. I can set this reminder now.",
    "ru": "Да, вы свободны. Могу поставить напоминание прямо сейчас.",
}

PREDICTIVE_REMINDER_KEYWORDS: dict[str, list[str]] = {
    "en": ["is that possible", "am i available", "can i do that", "do i have time"],
    "ru": ["это возможно", "я свободен", "могу ли я", "есть ли время", "получится ли"],
}


# ---------------------------------------------------------------------------
# Live templates (keyword → reply)
# ---------------------------------------------------------------------------

_TEMPLATES_EN: list[dict[str, Any]] = [
    {"id": "greeting", "keywords": ["hello", "hi", "hey", "good morning", "good evening"], "reply": "Hi. I'm here. Tell me what you need.", "priority": 1},
    {"id": "repeat", "keywords": ["repeat", "say again", "again", "what did you say"], "reply": "Sure. I can repeat that. What part should I repeat?", "priority": 2},
    {"id": "clarify", "keywords": ["you there", "can you hear me", "hello are you there"], "reply": "Yes, I can hear you. Please go ahead.", "priority": 3},
    {"id": "slow_down", "keywords": ["slow down", "too fast", "speak slower"], "reply": "Understood. I will speak slower.", "priority": 4},
    {"id": "volume_issue", "keywords": ["cant hear", "can't hear", "too quiet", "volume"], "reply": "Understood. I will keep replies short and clear.", "priority": 4},
    {"id": "availability_check", "keywords": ["am i free", "availability", "free tomorrow", "free at"], "reply": "Let me quickly check your availability.", "calendar_check": True, "priority": 10},
    {"id": "reminder_set", "keywords": ["set a reminder", "remind me", "set reminder", "reminder"], "reply": "Absolutely. Let me check your availability and queue this reminder.", "calendar_check": True, "calendar_enqueue": True, "priority": 11},
    {"id": "meeting_schedule", "keywords": ["schedule meeting", "book meeting", "add meeting", "create event"], "reply": "Absolutely. I'll check your timetable and queue this for scheduling.", "calendar_check": True, "calendar_enqueue": True, "priority": 11},
    {"id": "meeting_followup_details", "keywords": ["what time works", "propose a time", "find a slot", "next available slot"], "reply": "Sure. I'll check your availability and suggest the best slot.", "calendar_check": True, "calendar_enqueue": True, "priority": 12},
    {"id": "meeting_duration", "keywords": ["for 30 minutes", "for 1 hour", "for one hour", "duration"], "reply": "Noted. I'll include that duration when I schedule it.", "calendar_enqueue": True, "priority": 10},
    {"id": "calendar_today", "keywords": ["calendar", "today", "schedule", "upcoming"], "reply": "I can check your upcoming schedule now.", "calendar_check": True, "priority": 8},
    {"id": "calendar_delete", "keywords": ["delete event", "remove event", "cancel event"], "reply": "Okay. I can remove that event after you confirm which one.", "calendar_enqueue": True, "priority": 9},
    {"id": "calendar_move_day", "keywords": ["move to tomorrow", "move to monday", "move it to", "change day"], "reply": "Understood. I'll queue that reschedule request.", "calendar_enqueue": True, "priority": 10},
    {"id": "calendar_conflict", "keywords": ["conflict", "double booked", "overlap", "clash"], "reply": "Got it. I'll check conflicts and suggest an alternative.", "calendar_check": True, "calendar_enqueue": True, "priority": 12},
    {"id": "time_query", "keywords": ["what time", "when is", "next meeting"], "reply": "I can check that now. Give me one second.", "calendar_check": True, "priority": 7},
    {"id": "reschedule", "keywords": ["reschedule", "move meeting", "another time"], "reply": "Understood. I can help reschedule it.", "calendar_enqueue": True, "priority": 9},
    {"id": "reschedule_confirmation", "keywords": ["yes reschedule", "confirm reschedule", "go ahead reschedule"], "reply": "Great. I'll proceed with the reschedule request now.", "calendar_enqueue": True, "priority": 11},
    {"id": "reschedule_reject", "keywords": ["dont reschedule", "don't reschedule", "keep it", "leave it"], "reply": "Understood. I'll keep the current schedule unchanged.", "priority": 11},
    {"id": "confirm", "keywords": ["yes", "confirm", "correct", "go ahead"], "reply": "Great. Confirmed.", "priority": 1},
    {"id": "reject", "keywords": ["no", "not that", "wrong", "cancel that"], "reply": "Okay. I won't do that. Tell me the correct option.", "priority": 1},
    {"id": "thanks", "keywords": ["thanks", "thank you", "appreciate"], "reply": "You're welcome.", "priority": 1},
    {"id": "status_update", "keywords": ["status", "did you do it", "is it done", "update me"], "reply": "Sure. I'll check and give you a quick status update.", "calendar_check": True, "priority": 8},
    {"id": "urgent_priority", "keywords": ["urgent", "asap", "right now", "immediately"], "reply": "Understood. I'll mark this as urgent and process it first.", "calendar_enqueue": True, "priority": 12},
    {"id": "timezone_change", "keywords": ["my timezone", "in london time", "in utc", "time zone"], "reply": "Got it. I'll handle this in the correct timezone.", "calendar_enqueue": True, "priority": 9},
    {"id": "hold_on", "keywords": ["wait", "hold on", "one second"], "reply": "Sure, I'll wait.", "priority": 1},
    {"id": "goodbye", "keywords": ["bye", "goodbye", "hang up", "that is all"], "reply": "Got it. I'll wrap up now.", "priority": 2},
    {"id": "smalltalk_how_are_you", "keywords": ["how are you", "hows it going", "how are things"], "reply": "I'm good and ready to help. What would you like to schedule?", "priority": 2},
    {"id": "smalltalk_name", "keywords": ["who are you", "what are you", "your name"], "reply": "I'm your AI secretary. I can help with reminders and scheduling.", "priority": 2},
    {"id": "short_ack", "keywords": ["okay", "ok", "alright", "sounds good"], "reply": "Perfect. What's the next detail?", "priority": 1},
]

_TEMPLATES_RU: list[dict[str, Any]] = [
    {"id": "greeting", "keywords": ["привет", "здравствуйте", "добрый день", "добрый вечер", "алло"], "reply": "Здравствуйте. Слушаю вас.", "priority": 1},
    {"id": "repeat", "keywords": ["повтори", "повторите", "ещё раз", "что вы сказали"], "reply": "Конечно. Что именно повторить?", "priority": 2},
    {"id": "clarify", "keywords": ["вы тут", "вы здесь", "вы меня слышите", "алло вы тут"], "reply": "Да, слышу вас. Продолжайте.", "priority": 3},
    {"id": "slow_down", "keywords": ["помедленнее", "слишком быстро", "говорите медленнее"], "reply": "Понял. Буду говорить медленнее.", "priority": 4},
    {"id": "volume_issue", "keywords": ["не слышу", "плохо слышно", "тихо", "громкость"], "reply": "Понял. Буду отвечать коротко и чётко.", "priority": 4},
    {"id": "availability_check", "keywords": ["я свободен", "свободен ли я", "доступность", "свободен завтра"], "reply": "Сейчас проверю вашу доступность.", "calendar_check": True, "priority": 10},
    {"id": "reminder_set", "keywords": ["напомни", "поставь напоминание", "напоминание", "напомните"], "reply": "Конечно. Проверю расписание и поставлю напоминание.", "calendar_check": True, "calendar_enqueue": True, "priority": 11},
    {"id": "meeting_schedule", "keywords": ["назначь встречу", "забронируй встречу", "создай событие", "запланируй"], "reply": "Конечно. Проверю расписание и добавлю встречу.", "calendar_check": True, "calendar_enqueue": True, "priority": 11},
    {"id": "meeting_followup_details", "keywords": ["когда удобно", "предложи время", "найди слот", "ближайший слот"], "reply": "Проверю расписание и предложу лучшее время.", "calendar_check": True, "calendar_enqueue": True, "priority": 12},
    {"id": "meeting_duration", "keywords": ["на 30 минут", "на час", "на один час", "длительность"], "reply": "Учту длительность при планировании.", "calendar_enqueue": True, "priority": 10},
    {"id": "calendar_today", "keywords": ["календарь", "сегодня", "расписание", "ближайшие"], "reply": "Сейчас проверю ваше расписание.", "calendar_check": True, "priority": 8},
    {"id": "calendar_delete", "keywords": ["удали событие", "убери событие", "отмени событие"], "reply": "Могу удалить после подтверждения. Какое именно?", "calendar_enqueue": True, "priority": 9},
    {"id": "calendar_move_day", "keywords": ["перенеси на завтра", "перенеси на понедельник", "перенеси на", "смени день"], "reply": "Понял. Поставлю в очередь на перенос.", "calendar_enqueue": True, "priority": 10},
    {"id": "calendar_conflict", "keywords": ["конфликт", "наложение", "пересечение", "накладка"], "reply": "Понял. Проверю конфликты и предложу альтернативу.", "calendar_check": True, "calendar_enqueue": True, "priority": 12},
    {"id": "time_query", "keywords": ["во сколько", "когда", "следующая встреча"], "reply": "Сейчас проверю. Одну секунду.", "calendar_check": True, "priority": 7},
    {"id": "reschedule", "keywords": ["перенеси", "перенести встречу", "другое время"], "reply": "Понял. Могу помочь перенести.", "calendar_enqueue": True, "priority": 9},
    {"id": "reschedule_confirmation", "keywords": ["да перенеси", "подтверди перенос", "давай перенеси"], "reply": "Хорошо. Переношу сейчас.", "calendar_enqueue": True, "priority": 11},
    {"id": "reschedule_reject", "keywords": ["не переноси", "оставь как есть", "не надо"], "reply": "Понял. Оставляю расписание без изменений.", "priority": 11},
    {"id": "confirm", "keywords": ["да", "подтверждаю", "верно", "давай"], "reply": "Отлично. Подтверждено.", "priority": 1},
    {"id": "reject", "keywords": ["нет", "не то", "неправильно", "отмени"], "reply": "Хорошо. Не буду. Скажите правильный вариант.", "priority": 1},
    {"id": "thanks", "keywords": ["спасибо", "благодарю", "спс"], "reply": "Пожалуйста.", "priority": 1},
    {"id": "status_update", "keywords": ["статус", "сделал", "готово ли", "обнови"], "reply": "Сейчас проверю и дам обновление.", "calendar_check": True, "priority": 8},
    {"id": "urgent_priority", "keywords": ["срочно", "немедленно", "прямо сейчас", "как можно скорее"], "reply": "Понял. Отмечаю как срочное и обрабатываю первым.", "calendar_enqueue": True, "priority": 12},
    {"id": "timezone_change", "keywords": ["часовой пояс", "по лондону", "по utc", "таймзона"], "reply": "Понял. Учту часовой пояс.", "calendar_enqueue": True, "priority": 9},
    {"id": "hold_on", "keywords": ["подожди", "подождите", "секунду", "минуту"], "reply": "Хорошо, жду.", "priority": 1},
    {"id": "goodbye", "keywords": ["пока", "до свидания", "отбой", "это всё"], "reply": "Понял. Завершаю.", "priority": 2},
    {"id": "smalltalk_how_are_you", "keywords": ["как дела", "как ты", "как поживаешь"], "reply": "Всё отлично, готов помочь. Что запланировать?", "priority": 2},
    {"id": "smalltalk_name", "keywords": ["кто ты", "что ты", "как тебя зовут"], "reply": "Я ваш ИИ-секретарь. Помогаю с напоминаниями и расписанием.", "priority": 2},
    {"id": "short_ack", "keywords": ["ладно", "хорошо", "ок", "понятно"], "reply": "Отлично. Что дальше?", "priority": 1},
]

DEFAULT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "en": _TEMPLATES_EN,
    "ru": _TEMPLATES_RU,
}


# ---------------------------------------------------------------------------
# TTS voice defaults per language
# ---------------------------------------------------------------------------

DEFAULT_TTS_VOICE: dict[str, str] = {
    "en": "en-GB-SoniaNeural",
    "ru": "ru-RU-DmitryNeural",
}

# ---------------------------------------------------------------------------
# STT model defaults per language
# ---------------------------------------------------------------------------

DEFAULT_STT_MODEL: dict[str, str] = {
    "en": "small.en",
    "ru": "small",
}


# ---------------------------------------------------------------------------
# Lookup helper
# ---------------------------------------------------------------------------

def t(mapping: dict[str, str], lang: str) -> str:
    """Return the string for *lang*, falling back to English."""
    return mapping.get(lang, mapping.get("en", ""))


def t_dict(mapping: dict[str, dict[str, str]], lang: str) -> dict[str, str]:
    """Return the sub-dict for *lang*, falling back to English."""
    return mapping.get(lang, mapping.get("en", {}))


def get_templates(lang: str) -> list[dict[str, Any]]:
    """Return default live-reply templates for *lang*."""
    return DEFAULT_TEMPLATES.get(lang, DEFAULT_TEMPLATES.get("en", []))
