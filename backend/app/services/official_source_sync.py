"""Synchronize allow-listed Hyundai web-manual pages discovered through Tavily.

Tavily is a discovery transport only. The stored Hyundai page text and its
canonical URL are the evidence later shown to the user.
"""

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import OfficialSource, VehicleCatalog

# A Tavily result can include Hyundai marketing, newsroom, and dealer pages.
# They are official sites, but they are not an owner's manual and must never
# become RAG evidence.  Keep this MVP's web supplement inside the exact
# Digital Owner's Manual service.
_ALLOWED_HOSTS = {"ownersmanual.hyundai.com"}
_VEHICLE_INDEX_QUERY = "취급 설명서 경고등 심볼 site:ownersmanual.hyundai.com/manual/"
_VARIANT_PATTERN = re.compile(r"인포테인먼트\s*매뉴얼\s*\(([^)]+)\)", re.IGNORECASE)


class OfficialSourceSyncError(RuntimeError):
    pass


def resolve_official_sources(db: Session, catalog_id) -> list[OfficialSource]:
    return list(
        db.scalars(
            select(OfficialSource)
            .where(OfficialSource.catalog_id == catalog_id, OfficialSource.status == "READY")
            .order_by(OfficialSource.synced_at.desc())
        )
    )


async def sync_official_sources(
    db: Session, catalog: VehicleCatalog, settings: Settings | None = None
) -> list[OfficialSource]:
    settings = settings or get_settings()
    if not settings.tavily_api_key:
        raise OfficialSourceSyncError("TAVILY_API_KEY가 설정되지 않았습니다.")

    # URL is the identity of a web source.  Tavily may return the same page
    # for multiple query plans; consolidate before creating SQLAlchemy rows.
    fetched: dict[str, tuple[str, dict, str | None]] = {}
    async with httpx.AsyncClient(timeout=settings.official_source_sync_timeout_seconds) as client:
        index_results = await _tavily_search(
            client,
            settings,
            f"{catalog.model_name} {catalog.model_year} {_VEHICLE_INDEX_QUERY}",
        )
        for item in index_results:
            url = str(item.get("url", ""))
            if _is_catalog_source(url, "VEHICLE_MANUAL_INDEX", catalog) and str(item.get("content", "")).strip():
                fetched.setdefault(url, ("VEHICLE_MANUAL_INDEX", item, None))

        # The vehicle landing page is the entitlement boundary: only the
        # infotainment variants named there may be supplemented.  A system
        # detail page intentionally lacks the car name, so it is never added
        # unless the exact vehicle page first listed that system.
        variants = _declared_infotaiment_variants(
            str(item.get("content", "")) for _, item, _ in fetched.values()
        )
        for variant in variants:
            system_results = await _tavily_search(
                client,
                settings,
                f"{variant} 내비게이션 블루투스 설정 site:ownersmanual.hyundai.com/ivi/",
            )
            for item in system_results:
                url = str(item.get("url", ""))
                if _is_system_manual_source(url, variant) and str(item.get("content", "")).strip():
                    fetched.setdefault(url, ("INFOTAINMENT_WEB_MANUAL", item, variant))

    if not fetched:
        raise OfficialSourceSyncError("동기화할 현대 공식 웹 매뉴얼 본문을 찾지 못했습니다.")

    now = datetime.now(UTC)
    saved: list[OfficialSource] = []
    for url, (source_type, item, declared_variant) in fetched.items():
        content = _normalize_content(str(item["content"]))
        existing = db.scalar(
            select(OfficialSource).where(
                OfficialSource.catalog_id == catalog.id,
                OfficialSource.source_url == url,
            )
        )
        source = existing or OfficialSource(
            id=uuid4(),
            catalog_id=catalog.id,
            source_url=url,
            source_type=source_type,
            system_variant=declared_variant or _variant_from_url(url),
            title=str(item.get("title") or "현대 공식 웹 매뉴얼")[:500],
            content=content,
            content_sha256=_content_sha256(content),
            status="READY",
            synced_at=now,
        )
        if existing:
            source.source_type = source_type
            source.system_variant = declared_variant or _variant_from_url(url)
            source.title = str(item.get("title") or source.title)[:500]
            source.content = content
            source.content_sha256 = _content_sha256(content)
            source.status = "READY"
            source.synced_at = now
            source.ingestion_error = None
        else:
            db.add(source)
        saved.append(source)
    # A sync is a fresh, catalog-scoped snapshot.  Do not keep stale search
    # results (for example a previously accepted overseas manual) available
    # to the answer pipeline after the allow-list becomes stricter.
    active_urls = set(fetched)
    for existing in db.scalars(
        select(OfficialSource).where(OfficialSource.catalog_id == catalog.id)
    ):
        if existing.source_url not in active_urls:
            existing.status = "ARCHIVED"
    db.commit()
    return saved


def _is_allowed_official_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in _ALLOWED_HOSTS


def _is_catalog_source(url: str, source_type: str, catalog: VehicleCatalog) -> bool:
    """Accept only a known Digital Owner's Manual route for this catalog.

    Vehicle-index URLs must carry the selected model year and model name,
    preventing a different trim/year from being attached accidentally.
    """
    if not _is_allowed_official_url(url):
        return False
    parsed = urlparse(url)
    path = parsed.path.lower()
    if source_type == "VEHICLE_MANUAL_INDEX":
        query = parse_qs(parsed.query)
        year_matches = str(catalog.model_year) in query.get("year", [])
        model_matches = _compact(catalog.model_name) in _compact(unquote(parsed.path))
        return path.startswith("/manual/") and year_matches and model_matches
    return False


async def _tavily_search(
    client: httpx.AsyncClient, settings: Settings, query: str
) -> list[dict]:
    try:
        response = await client.post(
            f"{settings.tavily_base_url.rstrip('/')}/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": 4,
                "include_domains": ["ownersmanual.hyundai.com"],
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise OfficialSourceSyncError("현대 공식 웹 매뉴얼 검색에 실패했습니다.") from exc
    return [item for item in response.json().get("results", []) if isinstance(item, dict)]


def _declared_infotaiment_variants(contents) -> tuple[str, ...]:
    variants: list[str] = []
    for content in contents:
        for variant in _VARIANT_PATTERN.findall(content):
            cleaned = re.sub(r"\s+", " ", variant).strip()
            if cleaned and cleaned not in variants:
                variants.append(cleaned)
    return tuple(variants)


def _is_system_manual_source(url: str, variant: str) -> bool:
    if not _is_allowed_official_url(url):
        return False
    path = unquote(urlparse(url).path)
    lowered_path = path.lower()
    if not lowered_path.startswith("/ivi/"):
        return False
    route = path.split("/")[2] if len(path.split("/")) > 2 else ""
    # The app is Korean-market only.  A result carrying a Korean translation
    # of an overseas manual is still the wrong vehicle-market specification.
    is_korean_market = "/avnt/kor/korean/" in lowered_path
    return is_korean_market and _compact(route) in _variant_route_keys(variant)


def _variant_route_keys(variant: str) -> set[str]:
    key = _compact(variant)
    # The vehicle landing page spells one generation as STD_GEN5_WIDE while
    # the official URL spells the same family STD_GEN5W.
    aliases = {key}
    if key == "stdgen5wide":
        aliases.add("stdgen5w")
    if key.startswith("pleos"):
        aliases.add(key.removeprefix("pleos"))
    return aliases


def _compact(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _variant_from_url(url: str) -> str | None:
    lowered = url.lower()
    if "connect-l" in lowered:
        return "Pleos Connect-L"
    if "connect-s" in lowered:
        return "Pleos Connect-S"
    return None


def _normalize_content(content: str) -> str:
    return "\n".join(line.strip() for line in content.splitlines() if line.strip())[:50_000]


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
