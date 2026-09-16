"""Regression set for the user-facing question scenarios in docs/RAG_질문_시나리오_평가세트.md."""

from types import SimpleNamespace

import pytest

from app.services.rag_pipeline import (
    CarMeRagGuardrailMiddleware,
    meaningful_tokens,
    parse_intent_classification,
)


@pytest.fixture
def guardrail() -> CarMeRagGuardrailMiddleware:
    return CarMeRagGuardrailMiddleware(
        SimpleNamespace(
            rag_minimum_evidence_score=9.0,
            rag_minimum_topic_coverage=0.5,
            rag_minimum_score_gap=0.75,
            rag_max_context_chunks=4,
            rag_intent_llm_enabled=False,
        )
    )


@pytest.mark.parametrize(
    ("question", "history", "expected_intent", "uses_history"),
    [
        ("MAX A/C는 어떻게 켜?", [], "manual_question", False),
        ("오토 디포그를 끄고 싶어", [], "manual_question", False),
        ("블루투스 연결 방법 알려줘", [], "manual_question", False),
        ("주행 중 경고 문구가 떴어", [], "symptom", False),
        ("와이퍼 속도는 어디서 바꿔?", [], "manual_question", False),
        ("에어컨에서 찬 바람이 안 나와", [], "symptom", False),
        ("후진할 때 소리가 안 들려", [], "symptom", False),
        ("시동이 잘 안 걸리는 것 같아", [], "symptom", False),
        ("계기판에 이상 표시가 나왔어", [], "symptom", False),
        ("에어컨 냄새가 이상해", [], "symptom", False),
        ("이 차량의 옵션에 대해 알려줘", [], "vehicle_options", False),
        ("선택 사양은 어떤 게 있어?", [], "vehicle_options", False),
        ("기본 사양과 옵션 차이가 뭐야?", [], "vehicle_options", False),
        ("어떤 내용들을 알고 있어?", [], "manual_overview", False),
        ("이 매뉴얼 목차를 요약해줘", [], "manual_overview", False),
        ("매뉴얼에서 무엇을 알 수 있어?", [], "manual_overview", False),
        ("네비게이션 초기화 방법 알려줘", [], "manual_question", False),
        ("내비 업데이트는 어떻게 해?", [], "manual_question", False),
        ("휴대폰이 연결은 됐는데 음악이 안 나와", [], "symptom", False),
        ("문 잠금 설정을 바꾸고 싶어", [], "manual_question", False),
        ("오토 디포그가 뭐야?", [], "manual_question", False),
        ("방금 말한 기능은 어떻게 꺼?", [("user", "오토 디포그가 뭐야?")], "follow_up", True),
        ("그거를 다시 켜려면?", [("user", "블루투스 연결을 해제했어")], "follow_up", True),
        ("그럼 경고가 계속 뜨면?", [("user", "엔진 경고등이 켜졌어")], "follow_up", True),
        ("이 기능은 어떤 때 써?", [("user", "MAX A/C는 어떻게 켜?")], "follow_up", True),
        ("그 화면이 안 보여", [("user", "내비게이션 화면 설정 방법 알려줘")], "follow_up", True),
        ("그거", [], "casual", False),
        ("안녕", [], "casual", False),
        ("반려동물 모드가 있어?", [], "manual_question", False),
        ("엔진오일로 에어컨을 고칠 수 있어?", [], "manual_question", False),
    ],
)
def test_question_scenarios_have_a_permissive_fallback_intent(
    guardrail: CarMeRagGuardrailMiddleware,
    question: str,
    history: list[tuple[str, str]],
    expected_intent: str,
    uses_history: bool,
) -> None:
    analysis = guardrail.fallback_analysis(question, history)
    assert analysis.intent == expected_intent
    assert analysis.uses_history is uses_history


def test_typo_normalization_is_used_for_retrieval(guardrail: CarMeRagGuardrailMiddleware) -> None:
    analysis = guardrail.fallback_analysis("네비게이션 초기화 방법 알려줘")
    assert "내비게이션" in analysis.retrieval_query
    assert analysis.topic is not None and analysis.topic.key == "navigation"


def test_air_conditioning_symptom_expands_to_owner_manual_labels(
    guardrail: CarMeRagGuardrailMiddleware,
) -> None:
    analysis = guardrail.fallback_analysis("에어컨에서 찬 바람이 안 나와")
    assert "송풍구 개폐" in analysis.retrieval_query


def test_wiper_speed_question_expands_to_actual_control_labels(
    guardrail: CarMeRagGuardrailMiddleware,
) -> None:
    analysis = guardrail.fallback_analysis("와이퍼 속도는 어떻게 바꿔?")
    assert "속도 조절 노브" in analysis.retrieval_query


def test_follow_up_symptom_inherits_caution_but_not_facts(guardrail: CarMeRagGuardrailMiddleware) -> None:
    analysis = guardrail.fallback_analysis("그럼 경고가 계속 뜨면?", [("user", "엔진 경고등이 켜졌어")])
    assert analysis.intent == "follow_up"
    assert analysis.has_symptom is True


def test_korean_particles_do_not_hide_a_manual_search_term() -> None:
    assert "옵션" in meaningful_tokens("이 차량의 옵션에 대해 알려줘")
    assert "방법" not in meaningful_tokens("내비게이션 초기화 방법을 알려줘")


def test_llm_json_is_bounded_before_it_changes_search() -> None:
    parsed = parse_intent_classification('{"intent":"follow_up","uses_history":true}')
    assert parsed == {
        "intent": "follow_up",
        "uses_history": True,
    }
    assert parse_intent_classification('{"intent":"answer_everything"}') is None
