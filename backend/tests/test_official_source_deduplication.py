"""The official manual crawler may reach a page through several navigation paths."""

from app.services.official_source_sync import OfficialManualSection, _deduplicate_section_rows


def test_section_urls_can_be_deduplicated_before_database_write() -> None:
    first = OfficialManualSection(
        title="기기 등록하기",
        source_url="https://ownersmanual.hyundai.com/ivi/example.html#register",
        content="1. 신규 추가를 누르세요.",
    )
    duplicate = OfficialManualSection(
        title="기기 등록하기",
        source_url=first.source_url,
        content=first.content,
    )
    rows = [
        ("INFOTAINMENT_WEB_MANUAL", first.source_url, "STD_GEN5W", first),
        ("INFOTAINMENT_WEB_MANUAL", duplicate.source_url, "STD_GEN5W", duplicate),
    ]

    unique_rows = _deduplicate_section_rows(rows)

    assert [row[1] for row in unique_rows] == [first.source_url]
