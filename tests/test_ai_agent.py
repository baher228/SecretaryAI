from secretary_ai.core.config import Settings
from secretary_ai.domain.models import IntentType
from secretary_ai.services.ai_agent import SecretaryAIAgent


def build_agent() -> SecretaryAIAgent:
    settings = Settings(zai_api_key=None)
    return SecretaryAIAgent(settings)


def test_try_parse_json_accepts_plain_json_and_code_fence() -> None:
    agent = build_agent()

    plain = agent._try_parse_json('{"intent":"general_query","confidence":0.8}')
    fenced = agent._try_parse_json('```json\n{"intent":"reminder","confidence":0.9}\n```')

    assert plain.get("intent") == "general_query"
    assert fenced.get("intent") == "reminder"


def test_try_parse_json_extracts_embedded_object() -> None:
    agent = build_agent()

    parsed = agent._try_parse_json('Model output: {"intent":"book_event","confidence":0.5} trailing text')

    assert parsed.get("intent") == "book_event"


def test_normalize_response_clamps_confidence_and_adds_transfer_reason() -> None:
    agent = build_agent()

    response = agent._normalize_response(
        call_id="c1",
        parsed={
            "intent": "transfer_human",
            "confidence": 10,
            "reply": "",
            "requires_human": True,
            "transfer_reason": "",
            "action_items": ["  escalate  ", "", 123],
            "extracted_fields": "invalid",
        },
    )

    assert response.intent == IntentType.TRANSFER_HUMAN
    assert response.confidence == 1.0
    assert response.requires_human is True
    assert response.transfer_reason is not None
    assert response.reply != ""
    assert response.action_items == ["escalate", "123"]
    assert response.extracted_fields == {}


def test_heuristic_response_detects_intent_keywords() -> None:
    agent = build_agent()

    reminder = agent._heuristic_response("c2", "Please remind me tomorrow", {})
    booking = agent._heuristic_response("c3", "Can you schedule a meeting", {})

    assert reminder.intent == IntentType.REMINDER
    assert booking.intent == IntentType.BOOK_EVENT


def test_analyze_turn_falls_back_to_heuristic_without_api_key() -> None:
    agent = build_agent()

    response = __import__("asyncio").run(
        agent.analyze_turn("c4", "please reschedule my meeting", {})
    )

    assert response.intent == IntentType.RESCHEDULE_EVENT
    assert response.reply
