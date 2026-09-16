"""Regression coverage for choosing evidence across PDF and official web sources."""

from types import SimpleNamespace

from app.services.rag_pipeline import CarMeRagGuardrailMiddleware


def test_specific_web_procedure_outranks_broad_pdf_safety_notice() -> None:
    guardrail = CarMeRagGuardrailMiddleware()
    analysis = guardrail.fallback_analysis("블루투스 연결 방법 알려줘")
    broad_pdf_notice = SimpleNamespace(
        content=(
            "경고. 반드시 안전한 곳에 차를 정차한 후 휴대 전화를 연결하십시오. "
            "운전 중 전화번호를 눌러 전화 걸기를 시도하거나 통화하지 마십시오."
        )
    )
    web_procedure = SimpleNamespace(
        source_type="INFOTAINMENT_WEB_MANUAL",
        title="블루투스 기기 연결하기 - 등록된 기기 연결하기",
        content=(
            "블루투스 기기를 사용하려면 등록된 기기를 시스템에 연결해야 합니다.\n"
            "1. 전체 메뉴 화면에서 설정, 기기 연결, 기기 연결을 누르세요.\n"
            "2. 연결할 기기의 아이콘을 누르세요."
        ),
    )

    hits = guardrail.rank_chunks([broad_pdf_notice, web_procedure], analysis)

    assert hits[0].chunk is web_procedure
    assert guardrail.evidence_gate(analysis, hits).result_status == "GROUNDED"
