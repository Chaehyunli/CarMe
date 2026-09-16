"""Synchronize allow-listed Hyundai web-manual pages for one vehicle catalog.

Tavily is a discovery transport only. The stored Hyundai page text and its
canonical URL are the evidence later shown to the user.
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import parse_qs, unquote, urljoin, urlparse, urlunparse
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
_MAX_OFFICIAL_PAGE_BYTES = 2_000_000
_MAX_OFFICIAL_SECTION_CHARS = 6_000
_MAX_OFFICIAL_MANUAL_PAGES = 160
_OFFICIAL_CRAWL_CONCURRENCY = 8
_MANUAL_LINK_PATTERN = re.compile(
    r"(?:href|data-(?:prev|next))\s*=\s*[\"']([^\"']+?\.html(?:#[^\"']*)?)[\"']"
    r"|mainHover\(\s*[\"']([^\"']+?\.html)[\"']\s*\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OfficialManualSection:
    """A heading-scoped excerpt from one Hyundai Digital Owner's Manual page."""

    title: str
    source_url: str
    content: str


class _OfficialManualHtmlParser(HTMLParser):
    """Extract the readable heading hierarchy without browser automation.

    Hyundai's current web manuals expose accordion content in the static HTML.
    Reading that HTML is more complete and more stable than using a search
    provider's abbreviated result snippet.
    """

    _IGNORED_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "svg", "header", "nav", "footer"}
    )
    _BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"p", "li", "ol", "ul", "div", "section", "article", "br", "table", "tr"}
    )
    _SECTION_TAGS: ClassVar[frozenset[str]] = frozenset({"h2", "h3"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.document_title = ""
        self._ignored_depth = 0
        self._heading_tag: str | None = None
        self._heading_id: str | None = None
        self._heading_parts: list[str] = []
        self._current_title = ""
        self._current_anchor: str | None = None
        self._current_parts: list[str] = []
        self._ordered_list_counters: list[int] = []
        self.sections: list[tuple[str, str | None, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in {"h1", *self._SECTION_TAGS}:
            if tag in self._SECTION_TAGS:
                self._flush_section()
            self._heading_tag = tag
            self._heading_id = dict(attrs).get("id")
            self._heading_parts = []
            return
        if tag == "ol":
            self._ordered_list_counters.append(0)
            return
        if tag == "li" and self._current_title:
            if self._ordered_list_counters:
                self._ordered_list_counters[-1] += 1
                self._current_parts.append(f"\n{self._ordered_list_counters[-1]}. ")
            else:
                self._current_parts.append("\n- ")
            return
        if tag in self._BLOCK_TAGS and self._current_title:
            self._current_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag == "ol":
            if self._ordered_list_counters:
                self._ordered_list_counters.pop()
            return
        if self._heading_tag != tag:
            return
        heading = _normalize_content(" ".join(self._heading_parts))
        if tag == "h1":
            self.document_title = heading or self.document_title
        elif heading:
            self._current_title = heading
            self._current_anchor = self._heading_id
        self._heading_tag = None
        self._heading_id = None
        self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._heading_tag is not None:
            self._heading_parts.append(data)
        elif self._current_title:
            self._current_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_section()

    def _flush_section(self) -> None:
        if not self._current_title:
            return
        body = _normalize_content("".join(self._current_parts))
        if body:
            title = " - ".join(part for part in (self.document_title, self._current_title) if part)
            self.sections.append((title or self._current_title, self._current_anchor, body))
        self._current_title = ""
        self._current_anchor = None
        self._current_parts = []


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
    fetched: dict[str, tuple[str, dict, str | None]] = {}
    async with httpx.AsyncClient(timeout=settings.official_source_sync_timeout_seconds) as client:
        # The Hyundai vehicle page exposes an official API for the exact
        # infotainment variants attached to project code + model year.  This
        # is more reliable than a web search, especially for commercial
        # variants such as Sonata Taxi.
        for variant, url in await _vehicle_infotaiment_sources(client, catalog):
            fetched.setdefault(
                url,
                ("INFOTAINMENT_WEB_MANUAL", {"title": f"현대 {variant} 웹 매뉴얼"}, variant),
            )

        # Tavily is a fallback discovery route for catalogs whose official
        # vehicle API has no linked infotainment manual.  Its short result
        # snippets never become RAG evidence; only fetched Hyundai HTML does.
        if not fetched and settings.tavily_api_key:
            index_results = await _tavily_search(
                client,
                settings,
                f"{catalog.model_name} {catalog.model_year} {_VEHICLE_INDEX_QUERY}",
            )
            for item in index_results:
                url = str(item.get("url", ""))
                if _is_catalog_source(url, "VEHICLE_MANUAL_INDEX", catalog):
                    fetched.setdefault(url, ("VEHICLE_MANUAL_INDEX", item, None))

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
                    if _is_system_manual_source(url, variant):
                        fetched.setdefault(url, ("INFOTAINMENT_WEB_MANUAL", item, variant))

    if not fetched:
        raise OfficialSourceSyncError("동기화할 현대 공식 웹 매뉴얼 본문을 찾지 못했습니다.")

    now = datetime.now(UTC)
    section_rows: list[tuple[str, str, str | None, OfficialManualSection]] = []
    crawled_manuals: dict[str, dict[str, str]] = {}
    async with httpx.AsyncClient(timeout=settings.official_source_sync_timeout_seconds) as client:
        for url, (source_type, item, declared_variant) in fetched.items():
            try:
                if source_type == "INFOTAINMENT_WEB_MANUAL":
                    root_url = _official_manual_root_url(url)
                    pages = crawled_manuals.get(root_url)
                    if pages is None:
                        pages = await _crawl_official_manual_pages(client, url)
                        crawled_manuals[root_url] = pages
                else:
                    pages = {url: await _fetch_official_html(client, url)}
            except OfficialSourceSyncError:
                continue
            for page_url, html in pages.items():
                sections = _extract_official_sections(
                    html,
                    page_url,
                    fallback_title=str(item.get("title") or "현대 공식 웹 매뉴얼"),
                )
                for section in sections:
                    section_rows.append((source_type, section.source_url, declared_variant, section))

    if not section_rows:
        raise OfficialSourceSyncError("현대 공식 웹 매뉴얼의 검색 가능한 상세 본문을 찾지 못했습니다.")

    # One page can be reached from the index, previous/next navigation, and a
    # Tavily seed.  Store a section URL once even when the crawler encountered
    # it by more than one route; the database constraint is intentionally the
    # final safety net, not normal control flow.
    section_rows = _deduplicate_section_rows(section_rows)

    saved: list[OfficialSource] = []
    for source_type, section_url, declared_variant, section in section_rows:
        existing = db.scalar(
            select(OfficialSource).where(
                OfficialSource.catalog_id == catalog.id,
                OfficialSource.source_url == section_url,
            )
        )
        source = existing or OfficialSource(
            id=uuid4(),
            catalog_id=catalog.id,
            source_url=section_url,
            source_type=source_type,
            system_variant=declared_variant or _variant_from_url(section_url),
            title=section.title[:500],
            content=section.content,
            content_sha256=_content_sha256(section.content),
            status="READY",
            synced_at=now,
        )
        if existing:
            source.source_type = source_type
            source.system_variant = declared_variant or _variant_from_url(section_url)
            source.title = section.title[:500]
            source.content = section.content
            source.content_sha256 = _content_sha256(section.content)
            source.status = "READY"
            source.synced_at = now
            source.ingestion_error = None
        else:
            db.add(source)
        saved.append(source)
    # A sync is a fresh, catalog-scoped snapshot.  Do not keep stale search
    # results (for example a previously accepted overseas manual) available
    # to the answer pipeline after the allow-list becomes stricter.
    active_urls = {section.source_url for _, _, _, section in section_rows}
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


async def _vehicle_infotaiment_sources(
    client: httpx.AsyncClient, catalog: VehicleCatalog
) -> tuple[tuple[str, str], ...]:
    """Read the exact IVI variants that Hyundai assigns to this catalog."""
    if not catalog.official_manual_url or not _is_allowed_official_url(catalog.official_manual_url):
        return ()
    query = parse_qs(urlparse(catalog.official_manual_url).query)
    project_code = query.get("projCode", [""])[0]
    year = query.get("year", [str(catalog.model_year)])[0]
    lang_code = query.get("langCode", ["ko_KR"])[0]
    country_code = query.get("countryCode", ["A99"])[0]
    if not project_code:
        return ()
    try:
        response = await client.get(
            "https://ownersmanual.hyundai.com/api/v3/hmc/model/avn-manuals",
            params={
                "projectCode": project_code,
                "year": year,
                "langCode": lang_code,
                "countryCode": country_code,
            },
            headers={"Accept-Language": "ko-KR,ko;q=0.9", "User-Agent": "CarMe-RAG/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return ()
    sources: list[tuple[str, str]] = []
    for platform in payload.get("frontSeat", []) if isinstance(payload, dict) else []:
        if not isinstance(platform, dict):
            continue
        variant = str(platform.get("platformCode", "")).strip()
        for manual in platform.get("manuals", []):
            url = str(manual.get("url", "")).strip() if isinstance(manual, dict) else ""
            if variant and _is_system_manual_source(url, variant) and (variant, url) not in sources:
                sources.append((variant, url))
    return tuple(sources)


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


async def _fetch_official_html(client: httpx.AsyncClient, url: str) -> str:
    """Fetch the full allow-listed Hyundai page after Tavily discovers it."""
    try:
        response = await client.get(
            url,
            headers={"Accept-Language": "ko-KR,ko;q=0.9", "User-Agent": "CarMe-RAG/1.0"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OfficialSourceSyncError("현대 공식 웹 매뉴얼 본문을 불러오지 못했습니다.") from exc
    if not _is_allowed_official_url(str(response.url)):
        raise OfficialSourceSyncError("허용되지 않은 공식 웹 매뉴얼 주소로 이동했습니다.")
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type:
        raise OfficialSourceSyncError("현대 공식 웹 매뉴얼 응답이 HTML이 아닙니다.")
    if len(response.content) > _MAX_OFFICIAL_PAGE_BYTES:
        raise OfficialSourceSyncError("현대 공식 웹 매뉴얼 본문 크기가 제한을 초과했습니다.")
    return response.text


def _official_manual_root_url(url: str) -> str:
    """Return the Korean IVI manual directory that bounds a small crawl."""
    parsed = urlparse(url)
    directory = parsed.path.rsplit("/", 1)[0].rstrip("/") + "/"
    return urlunparse(parsed._replace(path=directory, params="", query="", fragment=""))


def _deduplicate_section_rows(
    rows: list[tuple[str, str, str | None, OfficialManualSection]],
) -> list[tuple[str, str, str | None, OfficialManualSection]]:
    unique_rows: dict[str, tuple[str, str, str | None, OfficialManualSection]] = {}
    for row in rows:
        unique_rows.setdefault(row[1], row)
    return list(unique_rows.values())


def _extract_official_manual_links(html: str, page_url: str, root_url: str) -> tuple[str, ...]:
    """Read static Hyundai navigation links without following arbitrary URLs."""
    root = urlparse(root_url)
    links: list[str] = []
    for match in _MANUAL_LINK_PATTERN.finditer(html):
        raw_link = unescape(next(value for value in match.groups() if value is not None))
        candidate = urlparse(urljoin(page_url, raw_link))
        if (
            candidate.scheme != root.scheme
            or candidate.netloc != root.netloc
            or not candidate.path.startswith(root.path)
            or not candidate.path.lower().endswith(".html")
        ):
            continue
        normalized = urlunparse(candidate._replace(params="", query="", fragment=""))
        if normalized not in links:
            links.append(normalized)
    return tuple(links)


async def _crawl_official_manual_pages(client: httpx.AsyncClient, seed_url: str) -> dict[str, str]:
    """Collect a bounded, same-manual snapshot for infotainment procedures.

    The Hyundai index uses JavaScript `mainHover('...html')` links, while
    category pages use ordinary anchors.  Both are static in the delivered
    HTML, so browser automation is unnecessary.  The directory boundary and
    page cap keep this an allow-listed manual sync, not a general web crawl.
    """
    root_url = _official_manual_root_url(seed_url)
    index_url = urljoin(root_url, "index.html")
    pending = [seed_url, index_url]
    seen: set[str] = set()
    pages: dict[str, str] = {}

    while pending and len(seen) < _MAX_OFFICIAL_MANUAL_PAGES:
        batch: list[str] = []
        while pending and len(batch) < _OFFICIAL_CRAWL_CONCURRENCY and len(seen) + len(batch) < _MAX_OFFICIAL_MANUAL_PAGES:
            candidate = pending.pop(0)
            if candidate not in seen:
                seen.add(candidate)
                batch.append(candidate)
        if not batch:
            continue
        results = await asyncio.gather(
            *(_fetch_official_html(client, page_url) for page_url in batch),
            return_exceptions=True,
        )
        for page_url, result in zip(batch, results, strict=True):
            if isinstance(result, Exception):
                continue
            pages[page_url] = result
            for linked_url in _extract_official_manual_links(result, page_url, root_url):
                if linked_url not in seen and linked_url not in pending:
                    pending.append(linked_url)
    return pages


def _extract_official_sections(
    html: str, source_url: str, *, fallback_title: str = "현대 공식 웹 매뉴얼"
) -> list[OfficialManualSection]:
    """Split a full official page into heading-scoped, searchable sections.

    The returned URL keeps Hyundai's fragment ID when one exists.  A generated
    fragment is only a stable database key for pages that omit heading IDs; it
    still opens the original official page in a browser.
    """
    parser = _OfficialManualHtmlParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # HTML is external and must not fail a whole sync silently.
        raise OfficialSourceSyncError("현대 공식 웹 매뉴얼 본문을 해석하지 못했습니다.") from exc

    base = urlunparse(urlparse(source_url)._replace(fragment=""))
    extracted: list[OfficialManualSection] = []
    for index, (title, anchor, body) in enumerate(parser.sections, start=1):
        section_url = f"{base}#{anchor or f'section-{index}'}"
        full_content = _normalize_content(f"{title}\n{body}")
        for part_number, content in enumerate(_split_official_section(full_content), start=1):
            part_suffix = "" if part_number == 1 else f" (계속 {part_number})"
            part_url = section_url if part_number == 1 else f"{section_url}-part-{part_number}"
            extracted.append(
                OfficialManualSection(
                    title=f"{title or fallback_title}{part_suffix}",
                    source_url=part_url,
                    content=content,
                )
            )
    if extracted:
        return extracted

    fallback = _normalize_content(_visible_html_text(html))
    if not fallback:
        return []
    return [OfficialManualSection(title=fallback_title, source_url=base, content=fallback)]


def _split_official_section(content: str) -> list[str]:
    """Keep one concrete procedure together, splitting only unusually long sections."""
    if len(content) <= _MAX_OFFICIAL_SECTION_CHARS:
        return [content]
    chunks: list[str] = []
    current = ""
    for line in content.splitlines():
        candidate = f"{current}\n{line}".strip() if current else line
        if current and len(candidate) > _MAX_OFFICIAL_SECTION_CHARS:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _visible_html_text(html: str) -> str:
    without_hidden = re.sub(
        r"<(?:script|style|noscript|svg|header|nav|footer)\b[^>]*>[\s\S]*?</(?:script|style|noscript|svg|header|nav|footer)>",
        " ",
        html,
        flags=re.IGNORECASE,
    )
    return _normalize_content(unescape(re.sub(r"<[^>]+>", "\n", without_hidden)))


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
