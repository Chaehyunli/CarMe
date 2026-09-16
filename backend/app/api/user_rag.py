# ruff: noqa: B008
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.vehicle_catalog import active_catalog_statement
from app.core.config import get_settings
from app.db.models import ManualChunk, OfficialSource, Vehicle, VehicleCatalog
from app.db.session import get_db
from app.schemas.rag import (
    ChatManualResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    CitationResponse,
    DownloadResponse,
    UserVehicleCreate,
    UserVehicleResponse,
)
from app.services.chat_sessions import (
    create_session,
    delete_session,
    get_session,
    grounded_answer,
    is_safety_question,
    resolve_manuals,
    resolve_official_sources,
    safety_escalation_answer,
)
from app.services.rag_pipeline import (
    CarMeRagGuardrailMiddleware,
    insufficient_evidence_answer,
)
from app.services.storage import PrivateStorage

vehicles_router = APIRouter(prefix="/vehicles", tags=["vehicles"])
chat_router = APIRouter(prefix="/chat-sessions", tags=["chat-sessions"])


def vehicle_response(vehicle: Vehicle, catalog: VehicleCatalog) -> UserVehicleResponse:
    return UserVehicleResponse(
        id=vehicle.id,
        catalog_id=catalog.id,
        nickname=vehicle.nickname,
        display_name=catalog.display_name,
        created_at=vehicle.created_at,
    )


@vehicles_router.get("", response_model=list[UserVehicleResponse])
def list_my_vehicles(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        vehicle_response(vehicle, catalog)
        for vehicle, catalog in db.execute(
            select(Vehicle, VehicleCatalog)
            .join(VehicleCatalog, VehicleCatalog.id == Vehicle.catalog_id)
            .where(Vehicle.user_id == current_user.id, Vehicle.deleted_at.is_(None))
            .order_by(Vehicle.created_at.desc())
        )
    ]


@vehicles_router.post("", response_model=UserVehicleResponse, status_code=status.HTTP_201_CREATED)
def add_my_vehicle(payload: UserVehicleCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    catalog = db.scalar(active_catalog_statement().where(VehicleCatalog.id == payload.catalog_id))
    if catalog is None:
        raise HTTPException(status_code=422, detail="현재 선택할 수 있는 차량 또는 준비된 대표 매뉴얼이 없습니다.")
    vehicle = Vehicle(id=uuid4(), user_id=current_user.id, catalog_id=catalog.id, nickname=payload.nickname.strip())
    db.add(vehicle)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 등록한 차량입니다.") from exc
    db.refresh(vehicle)
    return vehicle_response(vehicle, catalog)


def _owned_session(session_id: UUID, current_user):
    try:
        return get_session(session_id, current_user.id)
    except LookupError as exc:
        if str(exc) == "EXPIRED":
            raise HTTPException(status_code=410, detail="채팅 세션이 만료되었습니다. 새로 시작해 주세요.") from exc
        raise HTTPException(status_code=404, detail="채팅 세션을 찾을 수 없습니다.") from exc


def _owned_vehicle(db: Session, vehicle_id: UUID, user_id: UUID) -> Vehicle:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.user_id == user_id, Vehicle.deleted_at.is_(None)))
    if vehicle is None:
        raise HTTPException(status_code=404, detail="내 차량을 찾을 수 없습니다.")
    return vehicle


def _manual_responses(manuals):
    return [ChatManualResponse(id=manual.id, title=manual.title, manual_type=manual.manual_type, pdf_page_count=manual.pdf_page_count, is_primary=is_primary) for manual, is_primary in manuals]


@chat_router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def start_chat(payload: ChatSessionCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    vehicle = _owned_vehicle(db, payload.vehicle_id, current_user.id)
    manuals = resolve_manuals(db, vehicle)
    if not manuals:
        raise HTTPException(status_code=422, detail="이 차량에 검색 가능한 준비된 매뉴얼이 없습니다.")
    state = create_session(current_user.id, vehicle.id)
    return ChatSessionResponse(
        id=state.id,
        vehicle_id=vehicle.id,
        expires_at=state.last_used_at + timedelta(minutes=get_settings().chat_session_idle_ttl_minutes),
        manuals=_manual_responses(manuals),
    )


@chat_router.get("/{session_id}/manuals", response_model=list[ChatManualResponse])
def list_session_manuals(session_id: UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    state = _owned_session(session_id, current_user)
    vehicle = _owned_vehicle(db, state.vehicle_id, current_user.id)
    manuals = resolve_manuals(db, vehicle)
    return _manual_responses(manuals)


@chat_router.post("/{session_id}/manuals/{manual_id}/download-url", response_model=DownloadResponse)
def download_url(session_id: UUID, manual_id: UUID, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    state = _owned_session(session_id, current_user)
    vehicle = _owned_vehicle(db, state.vehicle_id, current_user.id)
    manuals = resolve_manuals(db, vehicle)
    manual = next((item for item, _ in manuals if item.id == manual_id), None)
    if manual is None:
        raise HTTPException(status_code=404, detail="현재 차량에 연결된 매뉴얼이 아닙니다.")
    return DownloadResponse(
        url=PrivateStorage(get_settings()).create_download_url(manual.object_key),
        filename=manual.original_filename,
        expires_at=datetime.now(UTC) + timedelta(seconds=get_settings().upload_url_ttl_seconds),
    )


@chat_router.post("/{session_id}/messages", response_model=ChatMessageResponse)
async def send_message(session_id: UUID, payload: ChatMessageCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    state = _owned_session(session_id, current_user)
    question = payload.content.strip()
    if is_safety_question(question):
        return ChatMessageResponse(
            result_status="SAFETY_ESCALATION",
            escalation=safety_escalation_answer(),
            expires_at=state.last_used_at + timedelta(minutes=get_settings().chat_session_idle_ttl_minutes),
        )
    vehicle = _owned_vehicle(db, state.vehicle_id, current_user.id)
    manuals = resolve_manuals(db, vehicle)
    guardrail = CarMeRagGuardrailMiddleware()
    analysis = await guardrail.before_agent(question, state.history)
    # Retrieve both scoped corpora before making an evidence decision.  A
    # broad safety paragraph in the owner PDF must not prevent a directly
    # matching, heading-level infotainment procedure from being considered.
    manual_hits = guardrail.wrap_tool_call(db, [manual.id for manual, _ in manuals], analysis)
    official_sources = resolve_official_sources(db, vehicle)
    candidates = [hit.chunk for hit in manual_hits]
    candidates.extend(official_sources)
    hits = guardrail.rank_chunks(candidates, analysis)[: get_settings().rag_max_context_chunks]
    decision = guardrail.evidence_gate(analysis, hits)
    if decision.result_status == "INSUFFICIENT_EVIDENCE":
        catalog = db.get(VehicleCatalog, vehicle.catalog_id)
        if catalog is not None and catalog.official_manual_url and _needs_web_manual_link(analysis):
            return ChatMessageResponse(
                result_status="INSUFFICIENT_EVIDENCE",
                answer=(
                    "현재 연결된 취급설명서에서는 요청하신 세부 절차를 확인하지 못했습니다. "
                    "내비게이션·인포테인먼트 기능은 현대 공식 웹 매뉴얼에서 확인해 주세요."
                ),
                official_manual_url=catalog.official_manual_url,
                official_manual_label="현대 공식 웹 매뉴얼 열기",
                expires_at=state.last_used_at + timedelta(minutes=get_settings().chat_session_idle_ttl_minutes),
            )
        return ChatMessageResponse(
            result_status="INSUFFICIENT_EVIDENCE",
            answer=insufficient_evidence_answer(),
            expires_at=state.last_used_at + timedelta(minutes=get_settings().chat_session_idle_ttl_minutes),
        )
    evidence = guardrail.before_model(decision)
    answer = await grounded_answer(
        question,
        list(evidence),
        state.history,
        response_mode=(
            "CLARIFYING"
            if decision.result_status == "CLARIFYING" and analysis.intent == "symptom"
            else "LIMITED_EVIDENCE"
            if decision.result_status == "CLARIFYING"
            else decision.result_status
        ),
    )
    if not guardrail.after_model(answer, evidence):
        return ChatMessageResponse(
            result_status="INSUFFICIENT_EVIDENCE",
            answer=insufficient_evidence_answer(),
            expires_at=state.last_used_at + timedelta(minutes=get_settings().chat_session_idle_ttl_minutes),
        )
    state.history = (state.history + [("user", question), ("assistant", answer)])[-8:]
    return ChatMessageResponse(
        result_status=decision.result_status,
        answer=answer,
        citations=[
            citation_response(hit.chunk, {manual.id: manual.title for manual, _ in manuals})
            for hit in decision.hits[:3]
        ],
        expires_at=state.last_used_at + timedelta(minutes=get_settings().chat_session_idle_ttl_minutes),
    )


@chat_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_chat(session_id: UUID, current_user=Depends(get_current_user)):
    delete_session(session_id, current_user.id)


def _needs_web_manual_link(analysis) -> bool:
    """Only delegate web-only infotainment domains after PDF evidence fails."""
    return analysis.topic is not None and analysis.topic.key in {"navigation", "bluetooth"}


def citation_response(chunk, manual_titles: dict[UUID, str]) -> CitationResponse:
    if isinstance(chunk, OfficialSource):
        return CitationResponse(
            manual_title=chunk.title,
            quote_text=" ".join(chunk.content.split())[:240],
            source_type=chunk.source_type,
            source_url=chunk.source_url,
        )
    if not isinstance(chunk, ManualChunk):
        raise TypeError("지원하지 않는 RAG 근거 유형입니다.")
    return CitationResponse(
        manual_id=chunk.manual_id,
        manual_title=manual_titles[chunk.manual_id],
        pdf_page_number=chunk.pdf_page_number,
        printed_page_number=chunk.printed_page_number,
        quote_text=chunk.content[:240],
    )
