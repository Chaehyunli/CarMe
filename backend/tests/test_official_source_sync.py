"""Safety boundaries for Tavily-discovered web-manual supplements."""

from types import SimpleNamespace

import pytest

from app.services.official_source_sync import (
    _declared_infotaiment_variants,
    _extract_official_manual_links,
    _is_allowed_official_url,
    _is_catalog_source,
    _is_system_manual_source,
    _normalize_content,
    _vehicle_infotaiment_sources,
)


def _catalog():
    return SimpleNamespace(model_name="아반떼", model_year=2025)


def test_only_digital_owners_manual_host_is_an_evidence_source() -> None:
    assert _is_allowed_official_url(
        "https://ownersmanual.hyundai.com/ivi/Connect-L/AVNT/KOR/Korean/010_Troubleshooting_5.html"
    )
    assert not _is_allowed_official_url("https://www.hyundai.com/kr/ko/e/vehicles/the-all-new-avante/intro")
    assert not _is_allowed_official_url("https://news.hyundai.com/global/main")


def test_system_source_must_match_a_variant_declared_by_the_vehicle_page() -> None:
    l_url = "https://ownersmanual.hyundai.com/ivi/Connect-L/AVNT/KOR/Korean/010_Troubleshooting_5.html"
    s_url = "https://ownersmanual.hyundai.com/ivi/Connect-S/AVNT/KOR/Korean/faq.html"
    assert _is_system_manual_source(l_url, "Pleos Connect-L")
    assert _is_system_manual_source(s_url, "Pleos Connect-S")
    assert not _is_system_manual_source(l_url, "Pleos Connect-S")
    assert not _is_system_manual_source(
        "https://ownersmanual.hyundai.com/ivi/Connect-L/AVNT/USA/Korean/010_Troubleshooting_5.html",
        "Pleos Connect-L",
    )


def test_variants_are_derived_from_the_catalog_landing_content() -> None:
    content = "메뉴. 인포테인먼트 매뉴얼 (STD_GEN5_WIDE). 인포테인먼트 매뉴얼 (STD_GEN5W). PDF"
    assert _declared_infotaiment_variants([content]) == ("STD_GEN5_WIDE", "STD_GEN5W")
    assert _is_system_manual_source(
        "https://ownersmanual.hyundai.com/ivi/STD_GEN5W/AVNT/KOR/Korean/010_Settings_navi2.html",
        "STD_GEN5_WIDE",
    )


def test_vehicle_manual_index_requires_exact_model_and_year() -> None:
    catalog = _catalog()
    exact = "https://ownersmanual.hyundai.com/manual/%EC%95%84%EB%B0%98%EB%96%BC?langCode=ko_KR&countryCode=A99&year=2025&projCode=CN7"
    wrong_year = "https://ownersmanual.hyundai.com/manual/%EC%95%84%EB%B0%98%EB%96%BC?langCode=ko_KR&countryCode=A99&year=2024&projCode=CN7"
    wrong_model = "https://ownersmanual.hyundai.com/manual/%EC%8F%98%EB%82%98%ED%83%80?langCode=ko_KR&countryCode=A99&year=2025"
    assert _is_catalog_source(exact, "VEHICLE_MANUAL_INDEX", catalog)
    assert not _is_catalog_source(wrong_year, "VEHICLE_MANUAL_INDEX", catalog)
    assert not _is_catalog_source(wrong_model, "VEHICLE_MANUAL_INDEX", catalog)


def test_web_excerpt_is_compacted_before_becoming_rag_context() -> None:
    assert _normalize_content("  블루투스 연결  \n\n  문제 해결  ") == "블루투스 연결\n문제 해결"


def test_ivi_manual_crawler_uses_static_menu_and_section_links_only() -> None:
    root = "https://ownersmanual.hyundai.com/ivi/STD_GEN5W/AVNT/KOR/Korean/"
    html = """
    <a href="007_Calling_btconnect.html#d2e17147">등록된 기기 연결하기</a>
    <a onclick="mainHover('006_Navigation.html')">내비게이션</a>
    <div data-next="010_Settings.html"></div>
    <a href="https://example.com/not-a-manual.html">외부 링크</a>
    <a href="../English/007_Calling.html">다른 언어</a>
    """

    assert _extract_official_manual_links(html, f"{root}index.html", root) == (
        f"{root}007_Calling_btconnect.html",
        f"{root}006_Navigation.html",
        f"{root}010_Settings.html",
    )


@pytest.mark.asyncio
async def test_vehicle_api_sources_keep_only_the_catalogs_korean_ivi_variants() -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "frontSeat": [
                    {
                        "platformCode": "ccNC",
                        "manuals": [
                            {"url": "https://ownersmanual.hyundai.com/ivi/ccNC/AVNT/KOR/Korean/index.html"},
                            {"url": "https://ownersmanual.hyundai.com/ivi/ccNC/AVNT/USA/Korean/index.html"},
                        ],
                    }
                ]
            }

    class Client:
        async def get(self, *_args, **_kwargs):
            return Response()

    catalog = SimpleNamespace(
        model_year=2025,
        official_manual_url="https://ownersmanual.hyundai.com/manual/test?projCode=DN8c&year=2025&langCode=ko_KR&countryCode=A99",
    )

    assert await _vehicle_infotaiment_sources(Client(), catalog) == (
        ("ccNC", "https://ownersmanual.hyundai.com/ivi/ccNC/AVNT/KOR/Korean/index.html"),
    )
