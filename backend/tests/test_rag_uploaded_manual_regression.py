"""Opt-in regression checks against the locally uploaded manual corpus.

Run with ``CARME_RUN_DB_REGRESSION=1 pytest -m database_regression`` after a
manual is prepared. This complements the hermetic 30-scenario unit suite.
"""

import os

import pytest
from sqlalchemy import select

from app.db.models import Manual, ManualChunk
from app.db.session import SessionLocal
from app.services.rag_pipeline import CarMeRagGuardrailMiddleware

pytestmark = pytest.mark.skipif(
    os.getenv("CARME_RUN_DB_REGRESSION") != "1",
    reason="Set CARME_RUN_DB_REGRESSION=1 to test locally ingested manuals.",
)


@pytest.mark.database_regression
@pytest.mark.parametrize(
    ("manual_title", "question", "ranked_page", "status", "cited_page"),
    [
        # 아반떼 CN7 2025: direct PDF procedure, symptom clarification,
        # and intentionally rejected web-only infotainment requests.
        ("아반떼 CN7 2025 매뉴얼", "오토 디포그는 어떻게 해제해?", 203, "GROUNDED", 203),
        ("아반떼 CN7 2025 매뉴얼", "와이퍼 속도는 어떻게 바꿔?", 179, "GROUNDED", 179),
        ("아반떼 CN7 2025 매뉴얼", "와셔액을 분출하려면 어떻게 해?", 180, "GROUNDED", 180),
        ("아반떼 CN7 2025 매뉴얼", "전자식 파킹 브레이크 해제 방법 알려줘", 243, "GROUNDED", 243),
        ("아반떼 CN7 2025 매뉴얼", "에어컨에서 찬 바람이 안 나와", 186, "CLARIFYING", 186),
        ("아반떼 CN7 2025 매뉴얼", "타이어 공기압 경고등이 켜졌어", 371, "GROUNDED", 371),
        ("아반떼 CN7 2025 매뉴얼", "블루투스 연결 방법 알려줘", 213, "INSUFFICIENT_EVIDENCE", None),
        ("아반떼 CN7 2025 매뉴얼", "내비게이션 초기화 방법 알려줘", 336, "INSUFFICIENT_EVIDENCE", None),
        ("아반떼 CN7 2025 매뉴얼", "어떤 내용들을 알고 있어?", 2, "GROUNDED", 2),
        # 쏘나타 택시 DN8c 2025: same intent families with different
        # printed structure and different relevant PDF pages.
        ("쏘나타 택시 DN8c 2025 매뉴얼", "오토 디포그는 어떻게 해제해?", 160, "GROUNDED", 160),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "와이퍼 속도는 어떻게 바꿔?", 145, "GROUNDED", 145),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "와셔액을 분출하려면 어떻게 해?", 146, "GROUNDED", 146),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "전자식 파킹 브레이크 해제 방법 알려줘", 190, "GROUNDED", 190),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "에어컨에서 찬 바람이 안 나와", 154, "CLARIFYING", 154),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "타이어 공기압 경고등이 켜졌어", 84, "GROUNDED", 84),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "블루투스 연결 방법 알려줘", 171, "INSUFFICIENT_EVIDENCE", None),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "내비게이션 초기화 방법 알려줘", 261, "INSUFFICIENT_EVIDENCE", None),
        ("쏘나타 택시 DN8c 2025 매뉴얼", "어떤 내용들을 알고 있어?", 13, "GROUNDED", 13),
    ],
)
def test_uploaded_manual_stage_regressions(
    manual_title: str, question: str, ranked_page: int, status: str, cited_page: int | None
) -> None:
    """Real-corpus regression across both administrator-uploaded PDFs."""
    with SessionLocal() as db:
        manual = db.scalar(select(Manual).where(Manual.title == manual_title))
        if manual is None:
            pytest.skip(f"{manual_title} 매뉴얼이 없습니다.")
        chunks = list(
            db.scalars(
                select(ManualChunk).where(ManualChunk.manual_id == manual.id)
            )
        )

    guardrail = CarMeRagGuardrailMiddleware()
    trace = guardrail.trace_candidates(question, chunks)

    assert trace.ranked_hits[0].chunk.pdf_page_number == ranked_page
    assert trace.decision.result_status == status
    assert [hit.chunk.pdf_page_number for hit in trace.decision.hits] == (
        [] if cited_page is None else [cited_page]
    )
