import pytest

from services.ticket_routing import (
    classify_ticket_route,
    heuristic_route,
    validate_routing_payload,
)


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    async def classify(self, text):
        if self.error:
            raise self.error
        return self.payload


@pytest.mark.parametrize(
    ("text", "department"),
    [
        ("\u041f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u043d\u044b\u0435 \u0437\u0432\u043e\u043d\u043a\u0438 \u043d\u0435 \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0430\u044e\u0442\u0441\u044f", "operator"),
        ("\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f", "developer"),
        ("\u0414\u043e\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u043e\u0432, \u0441 \u0444\u0430\u0439\u043b\u0430\u043c\u0438 \u0441\u0432\u044f\u0437\u0430\u043d\u043e", "operator"),
        ("\u0421\u0438\u0441\u0442\u0435\u043c\u043d\u0430\u044f \u043e\u0448\u0438\u0431\u043a\u0430", "developer"),
        ("\u0412 \u0447\u0430\u0442-\u0431\u043e\u0442\u0435 \u043f\u043e\u043c\u0435\u043d\u044f\u0442\u044c \u0441\u0440\u043e\u043a \u0441\u043b\u0443\u0436\u0435\u0431\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u043a\u0438", "bot_admin"),
        ("\u041d\u0443\u0436\u043d\u043e \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0448\u0430\u0431\u043b\u043e\u043d \u0441\u043b\u0443\u0436\u0435\u0431\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u043a\u0438", "documents"),
        ("\u041d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0444\u0430\u0439\u043b \u0441\u043b\u0443\u0436\u0435\u0431\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u043a\u0438", "operator"),
        ("\u041f\u043e\u0441\u043b\u0435 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u043f\u0435\u0440\u0435\u0441\u0442\u0430\u043b\u0438 \u0437\u0430\u0433\u0440\u0443\u0436\u0430\u0442\u044c\u0441\u044f", "developer"),
    ],
)
def test_required_heuristic_departments(text, department):
    assert heuristic_route(text).department == department


def test_ambiguous_request_needs_clarification():
    decision = heuristic_route("\u041d\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442")
    assert decision.department == "unknown"
    assert decision.routing_status == "needs_clarification"
    assert decision.clarification_question


@pytest.mark.parametrize(
    ("confidence", "status"),
    [
        (92, "auto_routed"),
        (80, "auto_routed"),
        (60, "needs_review"),
        (30, "needs_clarification"),
    ],
)
def test_confidence_statuses(confidence, status):
    decision = validate_routing_payload(
        {
            "department": "operator",
            "confidence": confidence,
            "reason": "test",
            "need_clarification": False,
        }
    )
    assert decision.routing_status == status


def test_invalid_department_falls_back_to_unknown():
    decision = validate_routing_payload(
        {
            "department": "office",
            "confidence": 91,
            "reason": "test",
            "need_clarification": False,
        }
    )
    assert decision.department == "unknown"
    assert decision.routing_status == "needs_review"


def test_confidence_above_100_is_normalized():
    decision = validate_routing_payload(
        {
            "department": "developer",
            "confidence": 130,
            "reason": "test",
            "need_clarification": False,
        }
    )
    assert decision.confidence == 100
    assert decision.routing_status == "auto_routed"


def test_need_clarification_overrides_high_confidence():
    decision = validate_routing_payload(
        {
            "department": "developer",
            "confidence": 80,
            "reason": "test",
            "need_clarification": True,
            "clarification_question": "Which system fails?",
        }
    )
    assert decision.department == "unknown"
    assert decision.routing_status == "needs_clarification"


@pytest.mark.asyncio
async def test_llm_unavailable_uses_fallback():
    decision = await classify_ticket_route(
        "\u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f",
        llm_client=FakeClient(error=RuntimeError("down")),
    )
    assert decision.department == "developer"
    assert decision.success is False
    assert decision.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_llm_invalid_department_is_safe():
    decision = await classify_ticket_route(
        "anything",
        llm_client=FakeClient(
            {
                "department": "office",
                "confidence": 95,
                "reason": "test",
                "need_clarification": False,
            }
        ),
    )
    assert decision.department == "unknown"
    assert decision.routing_status == "needs_review"
