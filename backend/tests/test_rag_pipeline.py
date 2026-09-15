from types import SimpleNamespace

import pytest

from app.services.rag_pipeline import CarMeRagGuardrailMiddleware


@pytest.fixture
def guardrail() -> CarMeRagGuardrailMiddleware:
    return CarMeRagGuardrailMiddleware(
        SimpleNamespace(
            rag_minimum_evidence_score=9.0,
            rag_minimum_topic_coverage=0.5,
            rag_minimum_score_gap=0.75,
            rag_minimum_diagnostic_signals=1,
            rag_max_context_chunks=4,
        )
    )


def chunk(page: int, content: str) -> SimpleNamespace:
    return SimpleNamespace(pdf_page_number=page, content=content)


def decision_for(guardrail: CarMeRagGuardrailMiddleware, question: str, candidates: list[SimpleNamespace]):
    analysis = guardrail.fallback_analysis(question)
    hits = guardrail.rank_chunks(candidates, analysis)
    return guardrail.evidence_gate(analysis, hits), hits


def test_air_conditioning_diagnosis_keeps_limited_manual_fact(guardrail: CarMeRagGuardrailMiddleware) -> None:
    decision, hits = decision_for(
        guardrail,
        "에어컨 고장난거 같아",
        [
            chunk(91, "오토 디포그 설정/해제 방법입니다. 에어컨 선택 버튼을 누르십시오."),
            chunk(77, "에어컨 냉매 및 압축기 윤활유량 점검. 냉매량이 부족하면 에어컨 성능이 저하됩니다. 이상이 발견되면 점검을 받으십시오."),
        ],
    )
    assert decision.result_status == "CLARIFYING"
    assert hits[0].chunk.pdf_page_number == 77


def test_air_conditioning_operation_uses_direct_feature_evidence(guardrail: CarMeRagGuardrailMiddleware) -> None:
    decision, hits = decision_for(
        guardrail,
        "오토 디포그는 어떻게 해제해?",
        [
            chunk(77, "에어컨 냉매 및 압축기 윤활유량 점검. 성능 저하 시 점검을 받으십시오."),
            chunk(91, "에어컨 공조 오토 디포그 설정/해제 방법. 시동 ON 상태에서 앞 유리창 서리제거 버튼을 3초 동안 누르십시오."),
        ],
    )
    assert decision.result_status == "GROUNDED"
    assert hits[0].chunk.pdf_page_number == 91


def test_cross_system_repair_claim_is_not_supported(guardrail: CarMeRagGuardrailMiddleware) -> None:
    decision, _ = decision_for(
        guardrail,
        "엔진오일로 에어컨을 고칠 수 있어?",
        [chunk(77, "냉매량이 부족하면 에어컨 성능이 저하됩니다. 이상이 발견되면 점검을 받으십시오.")],
    )
    assert decision.result_status == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize(
    ("question", "content"),
    [
        ("블루투스 연결 방법을 알려줘", "블루투스 핸즈프리 연결 방법. 휴대 전화를 연결하십시오."),
        ("MAX A/C는 어떻게 켜?", "에어컨 최대 냉방(MAX A/C). 온도 조절 노브를 MAX A/C 위치에 두십시오."),
    ],
)
def test_direct_feature_questions_can_pass(guardrail: CarMeRagGuardrailMiddleware, question: str, content: str) -> None:
    decision, _ = decision_for(guardrail, question, [chunk(10, content)])
    assert decision.result_status == "GROUNDED"


def test_navigation_only_hit_is_rejected(guardrail: CarMeRagGuardrailMiddleware) -> None:
    decision, _ = decision_for(
        guardrail,
        "에어컨 고장난거 같아",
        [chunk(5, "목차... 에어컨 시스템... 히터 및 에어컨... 냉매... 정기 점검...")],
    )
    assert decision.result_status == "INSUFFICIENT_EVIDENCE"


def test_unrelated_question_is_not_promoted_by_common_word(guardrail: CarMeRagGuardrailMiddleware) -> None:
    decision, _ = decision_for(
        guardrail,
        "반려동물을 위한 에어컨 모드는 있어?",
        [chunk(77, "에어컨 냉매 및 압축기 윤활유량 점검. 냉매량이 부족하면 성능이 저하됩니다.")],
    )
    # The topic is present but there is no direct evidence for a pet mode.
    assert decision.result_status == "INSUFFICIENT_EVIDENCE"


def test_non_actionable_comment_is_not_answered_as_manual_guidance(guardrail: CarMeRagGuardrailMiddleware) -> None:
    decision, _ = decision_for(
        guardrail,
        "에어컨이 예뻐",
        [chunk(77, "에어컨 냉매 및 압축기 윤활유량 점검. 냉매량이 부족하면 성능이 저하됩니다.")],
    )
    assert decision.result_status == "INSUFFICIENT_EVIDENCE"
