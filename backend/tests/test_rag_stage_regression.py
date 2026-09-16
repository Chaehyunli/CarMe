"""Thirty user scenarios asserted at every deterministic RAG stage.

These are deliberately model-free tests.  A local LLM may improve intent
classification at runtime, but it must not change whether a weak document
candidate is cited.  Each row verifies normalization/context, ranking, and
the evidence-gate result independently.
"""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.services.rag_pipeline import CarMeRagGuardrailMiddleware


def page(number: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(pdf_page_number=number, content=text)


DISTRACTOR = page(900, "운전 전에 안전벨트를 착용하십시오. 차량의 일반 주의 사항입니다.")
MAX_AC = page(74, "에어컨 MAX A/C 최대 냉방 설정 방법입니다. MAX A/C 버튼을 누르십시오.")
DEFOG = page(91, "오토 디포그 설정과 해제 방법입니다. 시동 ON에서 앞 유리창 서리제거 버튼을 3초 동안 누르십시오.")
BLUETOOTH = page(213, "블루투스 휴대 전화 연결 방법입니다. 기기 등록을 선택하고 연결을 완료하십시오.")
WARNING = page(370, "계기판 경고 문구가 표시되면 표시 문구와 경고등을 확인하십시오.")
WIPER = page(41, "와이퍼 스위치로 와이퍼 속도를 조절하는 방법입니다. 레버를 원하는 위치로 움직이십시오.")
AC_SYMPTOM = page(186, "에어컨 냉매량이 부족하면 냉방 성능이 저하될 수 있습니다. 이상이 있으면 점검을 받으십시오.")
REVERSE = page(87, "후진 시 경고음과 후방 주차 보조 시스템은 차량 사양에 따라 제공됩니다.")
START = page(151, "시동이 걸리지 않을 때는 변속 위치와 브레이크 페달 상태를 확인하십시오.")
OPTIONS = page(1, "차량의 선택 사양과 기본 사양은 트림 및 계약 조건에 따라 다를 수 있습니다.")
TOC = page(2, "목차 ... 안전 및 주의 사항 ... 차량 내부 ... 공조 ... 운전자 보조 ... 정기 점검")
NAV_LIMITATION = page(261, "내비게이션 지도 또는 GPS 정보에 오류가 있을 경우 운전자 보조 기능이 제한될 수 있습니다. 내비게이션이 재부팅될 수 있습니다.")
NAV_UPDATE = page(326, "내비게이션 소프트웨어 업데이트 중에는 일부 기능이 제한될 수 있습니다. 업데이트 안내를 확인하십시오.")
AUDIO = page(214, "블루투스 휴대폰이 연결되었지만 오디오 음악이 나오지 않을 때는 미디어 오디오 연결 상태를 확인하십시오.")
LOCK = page(105, "도어 잠금 설정 방법입니다. 도어 잠금 버튼과 사용자 설정 메뉴를 사용하십시오.")
NAV_SCREEN = page(330, "내비게이션 화면 설정 메뉴에서 지도 표시 방법을 선택할 수 있습니다.")


@dataclass(frozen=True)
class Scenario:
    question: str
    candidates: tuple[SimpleNamespace, ...]
    intent: str
    topic: str | None
    status: str
    ranked_page: int | None
    cited_page: int | None
    history: tuple[tuple[str, str], ...] = ()
    normalized_contains: str = ""
    uses_history: bool = False


SCENARIOS = (
    Scenario("MAX A/C는 어떻게 켜?", (MAX_AC, DISTRACTOR), "manual_question", "air_conditioning", "GROUNDED", 74, 74),
    Scenario("오토 디포그를 끄고 싶어", (DEFOG, AC_SYMPTOM), "manual_question", "air_conditioning", "GROUNDED", 91, 91),
    Scenario("블루투스 연결 방법 알려줘", (BLUETOOTH, DISTRACTOR), "manual_question", "bluetooth", "GROUNDED", 213, 213),
    Scenario("주행 중 경고 문구가 떴어", (WARNING, DISTRACTOR), "symptom", "warning", "CLARIFYING", 370, 370),
    Scenario("와이퍼 속도는 어디서 바꿔?", (WIPER, DISTRACTOR), "manual_question", "wiper", "GROUNDED", 41, 41),
    Scenario("에어컨에서 찬 바람이 안 나와", (AC_SYMPTOM, DEFOG), "symptom", "air_conditioning", "CLARIFYING", 186, 186),
    Scenario("후진할 때 소리가 안 들려", (REVERSE, DISTRACTOR), "symptom", "parking_assist", "CLARIFYING", 87, 87),
    Scenario("시동이 잘 안 걸리는 것 같아", (START, DISTRACTOR), "symptom", "starting", "CLARIFYING", 151, 151),
    Scenario("계기판에 이상 표시가 나왔어", (WARNING, DISTRACTOR), "symptom", "warning", "CLARIFYING", 370, 370),
    Scenario("에어컨 냄새가 이상해", (AC_SYMPTOM, DEFOG), "symptom", "air_conditioning", "CLARIFYING", 186, 186),
    Scenario("이 차량의 옵션에 대해 알려줘", (OPTIONS, DISTRACTOR), "vehicle_options", "vehicle_options", "GROUNDED", 1, 1),
    Scenario("선택 사양은 어떤 게 있어?", (OPTIONS, DISTRACTOR), "vehicle_options", "vehicle_options", "GROUNDED", 1, 1),
    Scenario("기본 사양과 옵션 차이가 뭐야?", (OPTIONS, DISTRACTOR), "vehicle_options", "vehicle_options", "GROUNDED", 1, 1),
    Scenario("어떤 내용들을 알고 있어?", (TOC, MAX_AC), "manual_overview", None, "GROUNDED", 2, 2),
    Scenario("이 매뉴얼 목차를 요약해줘", (TOC, MAX_AC), "manual_overview", None, "GROUNDED", 2, 2),
    Scenario("매뉴얼에서 무엇을 알 수 있어?", (TOC, MAX_AC), "manual_overview", None, "GROUNDED", 2, 2),
    Scenario("네비게이션 초기화 방법 알려줘", (NAV_LIMITATION, DISTRACTOR), "manual_question", "navigation", "INSUFFICIENT_EVIDENCE", 261, None, normalized_contains="내비게이션"),
    Scenario("내비 업데이트는 어떻게 해?", (NAV_UPDATE, NAV_LIMITATION), "manual_question", "navigation", "GROUNDED", 326, 326),
    Scenario("휴대폰이 연결은 됐는데 음악이 안 나와", (AUDIO, BLUETOOTH), "symptom", "bluetooth", "CLARIFYING", 214, 214),
    Scenario("문 잠금 설정을 바꾸고 싶어", (LOCK, DISTRACTOR), "manual_question", "door_lock", "GROUNDED", 105, 105),
    Scenario("오토 디포그가 뭐야?", (DEFOG, AC_SYMPTOM), "manual_question", "air_conditioning", "GROUNDED", 91, 91),
    Scenario("방금 말한 기능은 어떻게 꺼?", (DEFOG, MAX_AC), "follow_up", "air_conditioning", "GROUNDED", 91, 91, (("user", "오토 디포그가 뭐야?"),), uses_history=True),
    Scenario("그거를 다시 켜려면?", (BLUETOOTH, DISTRACTOR), "follow_up", "bluetooth", "GROUNDED", 213, 213, (("user", "블루투스 연결을 해제했어"),), uses_history=True),
    Scenario("그럼 경고가 계속 뜨면?", (WARNING, DISTRACTOR), "follow_up", "warning", "CLARIFYING", 370, 370, (("user", "엔진 경고등이 켜졌어"),), uses_history=True),
    Scenario("이 기능은 어떤 때 써?", (MAX_AC, DEFOG), "follow_up", "air_conditioning", "GROUNDED", 74, 74, (("user", "MAX A/C는 어떻게 켜?"),), uses_history=True),
    Scenario("그 화면이 안 보여", (NAV_SCREEN, DISTRACTOR), "follow_up", "navigation", "CLARIFYING", 330, 330, (("user", "내비게이션 화면 설정 방법 알려줘"),), uses_history=True),
    Scenario("그거", (MAX_AC,), "casual", None, "INSUFFICIENT_EVIDENCE", None, None),
    Scenario("안녕", (MAX_AC,), "casual", None, "INSUFFICIENT_EVIDENCE", None, None),
    Scenario("반려동물 모드가 있어?", (AC_SYMPTOM,), "manual_question", None, "INSUFFICIENT_EVIDENCE", None, None),
    Scenario("엔진오일로 에어컨을 고칠 수 있어?", (AC_SYMPTOM,), "manual_question", "air_conditioning", "INSUFFICIENT_EVIDENCE", 186, None),
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


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.question)
def test_every_user_scenario_has_a_stage_by_stage_contract(
    guardrail: CarMeRagGuardrailMiddleware, scenario: Scenario
) -> None:
    trace = guardrail.trace_candidates(scenario.question, scenario.candidates, scenario.history)

    # Stage 1: normalized search request and conversation binding.
    assert trace.analysis.intent == scenario.intent
    assert trace.analysis.uses_history is scenario.uses_history
    if scenario.normalized_contains:
        assert scenario.normalized_contains in trace.analysis.normalized_question
    assert (trace.analysis.topic.key if trace.analysis.topic else None) == scenario.topic

    # Stage 2: ranking. A rejected hit remains observable here, which is how
    # we prove the next stage—not the retriever—prevented a false citation.
    if scenario.ranked_page is None:
        assert not trace.ranked_hits
    else:
        assert trace.ranked_hits[0].chunk.pdf_page_number == scenario.ranked_page

    # Stage 3: only Evidence Gate output may be cited by the answer model.
    assert trace.decision.result_status == scenario.status
    assert [hit.chunk.pdf_page_number for hit in trace.decision.hits] == (
        [] if scenario.cited_page is None else [scenario.cited_page]
    )
