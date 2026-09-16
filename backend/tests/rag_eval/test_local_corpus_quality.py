"""End-to-end retrieval quality checks for the local READY corpus.

This is deliberately separate from the ordinary unit suite.  It reads the
administrator-prepared PDF chunks and cached official Hyundai web-manual
sections that are currently stored in the local database.

Run from ``backend`` with:

``CARME_RUN_RAG_EVAL=1 pytest tests/rag_eval -q -s``
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

import pytest
from sqlalchemy import select

from app.db.models import Manual, ManualApplicability, ManualStatus, OfficialSource, VehicleCatalog
from app.db.session import SessionLocal
from app.services.rag_pipeline import CarMeRagGuardrailMiddleware, EvidenceDecision, RetrievalHit

pytestmark = pytest.mark.skipif(
    os.getenv("CARME_RUN_RAG_EVAL") != "1",
    reason="Set CARME_RUN_RAG_EVAL=1 to run the local RAG quality evaluation.",
)


SourceKind = Literal["PDF", "OFFICIAL_WEB", "NONE"]


@dataclass(frozen=True)
class EvaluationScenario:
    """A stable, user-visible RAG expectation for the current local corpus."""

    id: str
    catalog_name: str
    question: str
    expected_status: str
    expected_source: SourceKind
    expected_title_fragment: str | None = None
    expected_pdf_page: int | None = None
    history: tuple[tuple[str, str], ...] = ()
    expected_intent: str = "manual_question"
    expected_uses_history: bool = False


@dataclass(frozen=True)
class EvaluationResult:
    scenario: EvaluationScenario
    decision: EvidenceDecision
    top_hit: RetrievalHit | None


# These are not synthetic chunks.  Every query is evaluated against the same
# combined candidate pool used by ``POST /chat-sessions/{id}/messages``:
# selected vehicle's READY PDF plus its cached official web-manual sections.
SCENARIOS = (
    EvaluationScenario(
        "AVN-WEB-001",
        "아반떼 2025",
        "블루투스 연결 방법 알려줘",
        "GROUNDED",
        "OFFICIAL_WEB",
        "기기 등록하기",
    ),
    EvaluationScenario(
        "AVN-WEB-002",
        "아반떼 2025",
        "등록된 기기를 연결하려면 어떻게 해?",
        "GROUNDED",
        "OFFICIAL_WEB",
        "등록된 기기 연결하기",
    ),
    EvaluationScenario(
        "SON-WEB-001",
        "쏘나타 택시 2025",
        "블루투스 연결 방법 알려줘",
        "GROUNDED",
        "OFFICIAL_WEB",
        "기기 등록하기",
    ),
    EvaluationScenario(
        "SON-WEB-002",
        "쏘나타 택시 2025",
        "등록된 기기를 연결하려면 어떻게 해?",
        "GROUNDED",
        "OFFICIAL_WEB",
        "등록된 기기 연결하기",
    ),
    EvaluationScenario(
        "AVN-PDF-001",
        "아반떼 2025",
        "오토 디포그는 어떻게 해제해?",
        "GROUNDED",
        "PDF",
        expected_pdf_page=203,
    ),
    EvaluationScenario(
        "SON-PDF-001",
        "쏘나타 택시 2025",
        "오토 디포그는 어떻게 해제해?",
        "GROUNDED",
        "PDF",
        expected_pdf_page=160,
    ),
    EvaluationScenario(
        "AVN-SYM-001",
        "아반떼 2025",
        "에어컨에서 찬 바람이 안 나와",
        "CLARIFYING",
        "PDF",
        expected_pdf_page=186,
        expected_intent="symptom",
    ),
    EvaluationScenario(
        "SON-SYM-001",
        "쏘나타 택시 2025",
        "에어컨에서 찬 바람이 안 나와",
        "CLARIFYING",
        "PDF",
        expected_pdf_page=154,
        expected_intent="symptom",
    ),
    EvaluationScenario(
        "AVN-FOLLOW-001",
        "아반떼 2025",
        "그럼 등록된 기기를 연결하려면 어떻게 해?",
        "GROUNDED",
        "OFFICIAL_WEB",
        "등록된 기기 연결하기",
        history=(("user", "블루투스로 휴대폰을 연결하고 싶어"),),
        expected_intent="follow_up",
        expected_uses_history=True,
    ),
    EvaluationScenario(
        "SON-NEG-001",
        "쏘나타 택시 2025",
        "엔진오일로 에어컨을 고칠 수 있어?",
        "INSUFFICIENT_EVIDENCE",
        "NONE",
    ),
    EvaluationScenario(
        "AVN-PDF-002",
        "아반떼 2025",
        "와이퍼 속도는 어떻게 바꿔?",
        "GROUNDED",
        "PDF",
        expected_pdf_page=179,
    ),
    EvaluationScenario(
        "SON-PDF-002",
        "쏘나타 택시 2025",
        "와이퍼 속도는 어떻게 바꿔?",
        "GROUNDED",
        "PDF",
        expected_pdf_page=145,
    ),
    EvaluationScenario(
        "AVN-PDF-003",
        "아반떼 2025",
        "와셔액을 분출하려면 어떻게 해?",
        "GROUNDED",
        "PDF",
        expected_pdf_page=180,
    ),
    EvaluationScenario(
        "SON-PDF-003",
        "쏘나타 택시 2025",
        "와셔액을 분출하려면 어떻게 해?",
        "GROUNDED",
        "PDF",
        expected_pdf_page=146,
    ),
    EvaluationScenario(
        "AVN-PDF-004",
        "아반떼 2025",
        "전자식 파킹 브레이크 해제 방법 알려줘",
        "GROUNDED",
        "PDF",
        expected_pdf_page=243,
    ),
    EvaluationScenario(
        "SON-PDF-004",
        "쏘나타 택시 2025",
        "전자식 파킹 브레이크 해제 방법 알려줘",
        "GROUNDED",
        "PDF",
        expected_pdf_page=190,
    ),
    EvaluationScenario(
        "AVN-PDF-005",
        "아반떼 2025",
        "타이어 공기압 경고등이 켜졌어",
        "GROUNDED",
        "PDF",
        expected_pdf_page=371,
    ),
    EvaluationScenario(
        "SON-PDF-005",
        "쏘나타 택시 2025",
        "타이어 공기압 경고등이 켜졌어",
        "GROUNDED",
        "PDF",
        expected_pdf_page=84,
    ),
    EvaluationScenario(
        "AVN-WEB-003",
        "아반떼 2025",
        "내비게이션 지도 글자 크기는 어떻게 바꿔?",
        "GROUNDED",
        "OFFICIAL_WEB",
        "지도 글자 크기",
    ),
    EvaluationScenario(
        "SON-WEB-003",
        "쏘나타 택시 2025",
        "내비게이션 지도 글자 크기는 어떻게 바꿔?",
        "GROUNDED",
        "OFFICIAL_WEB",
        "지도 글자 크기",
    ),
    EvaluationScenario(
        "AVN-WEB-004",
        "아반떼 2025",
        "블루투스로 음악 듣는 방법 알려줘",
        "GROUNDED",
        "OFFICIAL_WEB",
        "블루투스로 음악 듣기",
    ),
    EvaluationScenario(
        "SON-WEB-004",
        "쏘나타 택시 2025",
        "블루투스로 음악 듣는 방법 알려줘",
        "GROUNDED",
        "OFFICIAL_WEB",
        "블루투스 오디오 화면",
    ),
    EvaluationScenario(
        "AVN-PDF-006",
        "아반떼 2025",
        "가능한 옵션 정보를 모두 알려줘",
        "INSUFFICIENT_EVIDENCE",
        "NONE",
        expected_intent="vehicle_options",
    ),
    EvaluationScenario(
        "SON-PDF-006",
        "쏘나타 택시 2025",
        "가능한 옵션 정보를 모두 알려줘",
        "INSUFFICIENT_EVIDENCE",
        "NONE",
        expected_intent="vehicle_options",
    ),
    EvaluationScenario(
        "AVN-NEG-001",
        "아반떼 2025",
        "하늘을 날 수 있어?",
        "INSUFFICIENT_EVIDENCE",
        "NONE",
    ),
    EvaluationScenario(
        "SON-NEG-002",
        "쏘나타 택시 2025",
        "하늘을 날 수 있어?",
        "INSUFFICIENT_EVIDENCE",
        "NONE",
    ),
)


def _ready_corpus(db, catalog_name: str) -> tuple[list, list[OfficialSource]]:
    catalog = db.scalar(select(VehicleCatalog).where(VehicleCatalog.display_name == catalog_name))
    if catalog is None:
        pytest.fail(f"평가 대상 차량이 없습니다: {catalog_name}")

    manuals = list(
        db.scalars(
            select(Manual)
            .join(ManualApplicability, ManualApplicability.manual_id == Manual.id)
            .where(
                ManualApplicability.catalog_id == catalog.id,
                Manual.status == ManualStatus.READY,
            )
            .order_by(Manual.title)
        )
    )
    if not manuals:
        pytest.fail(f"{catalog_name}에 READY PDF 매뉴얼이 없습니다. 임베딩을 먼저 완료하세요.")

    official_sources = list(
        db.scalars(
            select(OfficialSource)
            .where(OfficialSource.catalog_id == catalog.id, OfficialSource.status == "READY")
            .order_by(OfficialSource.synced_at.desc())
        )
    )
    if not official_sources:
        pytest.fail(f"{catalog_name}에 READY 공식 웹 안내가 없습니다. 공식 안내 갱신을 먼저 실행하세요.")
    return manuals, official_sources


def run_scenario(scenario: EvaluationScenario) -> EvaluationResult:
    """Mirror the production combined-retrieval route without chat generation."""
    guardrail = CarMeRagGuardrailMiddleware()
    analysis = guardrail.fallback_analysis(scenario.question, scenario.history)
    with SessionLocal() as db:
        manuals, official_sources = _ready_corpus(db, scenario.catalog_name)
        pdf_hits = guardrail.wrap_tool_call(db, [manual.id for manual in manuals], analysis)
        candidates = [hit.chunk for hit in pdf_hits]
        candidates.extend(official_sources)
        ranked_hits = guardrail.rank_chunks(candidates, analysis)[: guardrail.settings.rag_max_context_chunks]
        decision = guardrail.evidence_gate(analysis, ranked_hits)
    return EvaluationResult(scenario, decision, ranked_hits[0] if ranked_hits else None)


def _source_kind(result: EvaluationResult) -> SourceKind:
    if result.decision.result_status == "INSUFFICIENT_EVIDENCE" or result.top_hit is None:
        return "NONE"
    return "OFFICIAL_WEB" if isinstance(result.top_hit.chunk, OfficialSource) else "PDF"


def _diagnostic(result: EvaluationResult) -> str:
    hit = result.top_hit
    if hit is None:
        source = "없음"
        title = "-"
        location = "-"
        score = "-"
    elif isinstance(hit.chunk, OfficialSource):
        source = "공식 웹 안내"
        title = hit.chunk.title
        location = hit.chunk.source_url
        score = f"{hit.score:.3f}"
    else:
        source = "PDF"
        title = "PDF 청크"
        location = f"PDF {hit.chunk.pdf_page_number}쪽"
        score = f"{hit.score:.3f}"
    return (
        f"[{result.scenario.id}] {result.decision.result_status} | {source} | "
        f"{title} | {location} | score={score} | 사유={result.decision.reason}"
    )


@pytest.mark.rag_evaluation
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.id)
def test_ready_corpus_matches_rag_quality_expectation(scenario: EvaluationScenario, capsys) -> None:
    """Check response status and whether the selected citation answers the question."""
    result = run_scenario(scenario)
    print(_diagnostic(result))

    assert result.decision.result_status == scenario.expected_status
    assert _source_kind(result) == scenario.expected_source

    if scenario.expected_title_fragment is not None:
        assert result.top_hit is not None
        assert isinstance(result.top_hit.chunk, OfficialSource)
        assert scenario.expected_title_fragment in result.top_hit.chunk.title
    if scenario.expected_pdf_page is not None:
        assert result.top_hit is not None
        assert not isinstance(result.top_hit.chunk, OfficialSource)
        assert result.top_hit.chunk.pdf_page_number == scenario.expected_pdf_page


@pytest.mark.rag_evaluation
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.id)
def test_agent_entry_preserves_expected_intent_and_session_scope(scenario: EvaluationScenario) -> None:
    """Validate the deterministic before-agent stage independently of retrieval."""
    analysis = CarMeRagGuardrailMiddleware().fallback_analysis(scenario.question, scenario.history)
    assert analysis.intent == scenario.expected_intent
    assert analysis.uses_history is scenario.expected_uses_history


@pytest.mark.rag_evaluation
def test_ready_corpus_evaluation_has_balanced_coverage() -> None:
    """Keep the suite representative instead of overfitting to one source type."""
    assert {scenario.catalog_name for scenario in SCENARIOS} == {"아반떼 2025", "쏘나타 택시 2025"}
    assert {scenario.expected_source for scenario in SCENARIOS} == {"PDF", "OFFICIAL_WEB", "NONE"}
    assert any(scenario.history for scenario in SCENARIOS)
