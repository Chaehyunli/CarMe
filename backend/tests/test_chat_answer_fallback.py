"""Readable evidence-only fallback when the local answer model is unavailable."""

from types import SimpleNamespace

from app.services.chat_sessions import _evidence_fallback


def test_procedure_fallback_uses_numbered_steps_instead_of_raw_manual_text() -> None:
    source = SimpleNamespace(
        content=(
            "블루투스 기기 연결하기 - 기기 등록하기\n"
            "1. 전체 메뉴에서 설정, 기기 연결, 기기 연결, 신규 추가를 누르세요.\n"
            "2. 연결할 기기를 선택하고 인증 번호를 확인하세요."
        )
    )

    answer = _evidence_fallback(source, "GROUNDED")

    assert answer.startswith("다음 순서로 진행해 보세요.\n\n방법\n1.")
    assert "2. 연결할 기기를 선택" in answer
    assert "블루투스 기기 연결하기" not in answer


def test_pdf_fallback_removes_page_and_extractor_artifacts() -> None:
    source = SimpleNamespace(
        content="5-5 73 블루투스 핸즈프리 2C_SteeringWheelCallButton 안전한 곳에 정차한 후 휴대 전화를 연결하십시오."
    )

    answer = _evidence_fallback(source, "GROUNDED")

    assert "5-5 73" not in answer
    assert "2C_SteeringWheelCallButton" not in answer
    assert "안전한 곳에 정차" in answer
