"""Regression tests for heading-level Hyundai web-manual retrieval."""

from types import SimpleNamespace

import pytest

from app.services.official_source_sync import _extract_official_sections
from app.services.rag_pipeline import CarMeRagGuardrailMiddleware

OFFICIAL_MANUAL_HTML = """
<html><body>
  <header>현대자동차</header>
  <main>
    <h1>블루투스 기기 연결하기</h1>
    <h2 id="register">기기 등록하기</h2>
    <p>블루투스 기기를 시스템에 등록해야 합니다.</p>
    <ol><li>전체 메뉴에서 설정, 기기 연결, 기기 연결, 신규 추가를 누르세요.</li>
    <li>휴대폰에서 차량 시스템을 선택하고 인증 번호가 같은지 확인해 연결을 승인하세요.</li></ol>
    <h2 id="connect">등록된 기기 연결하기</h2>
    <p>등록된 블루투스 기기를 시스템에 연결해야 합니다.</p>
    <ol><li>전체 메뉴에서 설정, 기기 연결, 기기 연결을 누르세요.</li>
    <li>연결할 기기의 아이콘을 누르세요.</li></ol>
    <h2 id="disconnect">등록된 기기 연결 해제하기</h2>
    <ol><li>전체 메뉴에서 설정, 기기 연결, 기기 연결을 누르세요.</li>
    <li>연결된 기기의 아이콘을 눌러 연결을 해제하세요.</li></ol>
    <h2 id="navigation">목적지 검색하기</h2>
    <ol><li>전체 메뉴에서 내비게이션을 누르세요.</li>
    <li>검색어를 입력해 목적지를 선택하세요.</li></ol>
    <h2 id="voice">음성으로 전화 걸기</h2>
    <ol><li>스티어링 휠의 음성 인식 버튼을 누르세요.</li>
    <li>전화할 사람의 이름을 말하세요.</li></ol>
  </main>
</body></html>
"""


@pytest.fixture
def sections():
    return _extract_official_sections(
        OFFICIAL_MANUAL_HTML,
        "https://ownersmanual.hyundai.com/ivi/STD_GEN5W/AVNT/KOR/Korean/007_Calling_btconnect.html",
    )


@pytest.fixture
def guardrail() -> CarMeRagGuardrailMiddleware:
    return CarMeRagGuardrailMiddleware(
        SimpleNamespace(
            rag_minimum_evidence_score=3.0,
            rag_minimum_topic_coverage=0.5,
            rag_minimum_score_gap=0.0,
            rag_max_context_chunks=4,
            rag_intent_llm_enabled=False,
        )
    )


def test_html_sections_keep_heading_text_and_official_fragment_urls(sections) -> None:
    titles = [section.title for section in sections]
    urls = [section.source_url for section in sections]
    assert any(title.endswith("기기 등록하기") for title in titles)
    assert any(title.endswith("등록된 기기 연결하기") for title in titles)
    assert any(url.endswith("#register") for url in urls)
    assert any("신규 추가" in section.content for section in sections)


@pytest.mark.parametrize(
    ("question", "expected_heading"),
    [
        ("새 블루투스 기기를 등록하는 방법 알려줘", "기기 등록하기"),
        ("등록된 블루투스 기기를 다시 연결하려면 어떻게 해?", "등록된 기기 연결하기"),
        ("연결된 블루투스 기기를 해제하는 방법 알려줘", "등록된 기기 연결 해제하기"),
        ("내비게이션에서 목적지를 검색하는 방법 알려줘", "목적지 검색하기"),
        ("음성으로 전화를 거는 방법 알려줘", "음성으로 전화 걸기"),
    ],
)
def test_web_manual_procedures_choose_the_specific_section(
    guardrail: CarMeRagGuardrailMiddleware, sections, question: str, expected_heading: str
) -> None:
    candidates = [SimpleNamespace(title=section.title, content=section.content) for section in sections]
    analysis = guardrail.fallback_analysis(question)
    hits = guardrail.rank_chunks(candidates, analysis)

    assert hits
    assert expected_heading in hits[0].chunk.title
    assert guardrail.evidence_gate(analysis, hits).result_status == "GROUNDED"


def test_bluetooth_heading_without_steps_is_not_accepted_as_a_procedure(
    guardrail: CarMeRagGuardrailMiddleware,
) -> None:
    synopsis = SimpleNamespace(
        title="블루투스 기기 연결하기",
        content="블루투스 기기를 사용하려면 기기 등록하기를 참고하세요.",
        source_type="INFOTAINMENT_WEB_MANUAL",
    )
    analysis = guardrail.fallback_analysis("블루투스 연결 방법 알려줘")
    hits = guardrail.rank_chunks([synopsis], analysis)

    assert hits
    assert guardrail.evidence_gate(analysis, hits).result_status == "INSUFFICIENT_EVIDENCE"
