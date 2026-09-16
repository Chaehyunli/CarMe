"""Create or resume local Ollama embeddings for uploaded CarMe PDFs.

Examples:
  python scripts/embed_manuals.py --status
  python scripts/embed_manuals.py --all
  python scripts/embed_manuals.py --all --rebuild
  python scripts/embed_manuals.py --manual-id <UUID> --rebuild
  python scripts/embed_manuals.py --resume
"""

import argparse
import sys
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.db.models import Manual, ManualStatus
from app.db.session import SessionLocal
from app.services.manual_ingestion import embed_manual_in_background, prepare_manual_for_indexing


def timestamp() -> str:
    return datetime.now(UTC).astimezone().strftime("%H:%M:%S")


def progress(title: str, completed: int, total: int) -> None:
    percent = 0 if total == 0 else completed / total * 100
    print(f"[{timestamp()}] {title}: {completed:,}/{total:,} 청크 ({percent:5.1f}%)", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="업로드된 PDF의 Ollama 임베딩을 생성합니다.")
    selection = parser.add_mutually_exclusive_group(required=False)
    selection.add_argument(
        "--all",
        action="store_true",
        help="UPLOADED/FAILED 문서를 준비하고, INDEXING 문서는 이어서 처리합니다.",
    )
    selection.add_argument("--manual-id", type=UUID, help="처리할 manual UUID 하나")
    selection.add_argument("--resume", action="store_true", help="INDEXING 상태 문서를 이어서 처리합니다.")
    parser.add_argument("--rebuild", action="store_true", help="READY 문서도 청크와 임베딩을 다시 만듭니다.")
    parser.add_argument("--status", action="store_true", help="문서별 상태·진행률만 출력합니다.")
    return parser.parse_args()


def print_status(db) -> list[Manual]:
    manuals = list(db.scalars(select(Manual).order_by(Manual.title)))
    if not manuals:
        print("등록된 매뉴얼이 없습니다.")
        return manuals
    for manual in manuals:
        total = manual.indexing_total_chunks
        progress_text = f"{manual.embedded_chunk_count:,}/{total:,}" if total else "-"
        error = f" | 오류: {manual.ingestion_error}" if manual.ingestion_error else ""
        print(f"{manual.id} | {manual.status.value:9} | {progress_text:>13} | {manual.title}{error}")
    return manuals


def selected_manuals(db, args: argparse.Namespace) -> list[Manual]:
    if args.manual_id:
        manual = db.get(Manual, args.manual_id)
        if manual is None:
            raise ValueError(f"manual_id={args.manual_id} 문서를 찾지 못했습니다.")
        return [manual]
    if args.resume:
        return list(db.scalars(select(Manual).where(Manual.status == ManualStatus.INDEXING).order_by(Manual.title)))
    # `--all` is deliberately recovery-friendly: a previously interrupted
    # INDEXING job must not be silently excluded from a subsequent full run.
    states = [ManualStatus.UPLOADED, ManualStatus.FAILED, ManualStatus.INDEXING]
    if args.rebuild:
        states.append(ManualStatus.READY)
    return list(db.scalars(select(Manual).where(Manual.status.in_(states)).order_by(Manual.title)))


def run_one(manual_id: UUID, args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        manual = db.get(Manual, manual_id)
        if manual is None:
            return
        if manual.status == ManualStatus.INDEXING:
            if not (args.resume or args.all):
                print(f"건너뜀: {manual.title}은 이미 INDEXING입니다. 재개하려면 --resume을 사용하세요.")
                return
            print(f"재개: {manual.title}")
        else:
            force = args.rebuild or manual.status == ManualStatus.READY
            pages, chunks = prepare_manual_for_indexing(db, manual, force=force)
            print(f"준비 완료: {manual.title} | {pages}쪽 | {chunks:,} 청크", flush=True)
    embed_manual_in_background(manual_id, progress)
    with SessionLocal() as db:
        completed = db.get(Manual, manual_id)
        if completed is None:
            return
        if completed.status == ManualStatus.READY:
            print(f"완료: {completed.title} | {completed.embedded_chunk_count:,}개 벡터 저장", flush=True)
        else:
            print(f"실패: {completed.title} | {completed.ingestion_error or completed.status.value}", file=sys.stderr, flush=True)


def main() -> int:
    args = parse_args()
    try:
        with SessionLocal() as db:
            print_status(db)
            if args.status:
                return 0
            targets = selected_manuals(db, args)
    except OperationalError:
        print("DB에 연결할 수 없습니다. 먼저 프로젝트의 PostgreSQL 컨테이너를 실행하세요.", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not targets:
        print("처리할 문서가 없습니다. READY 문서를 다시 만들려면 --all --rebuild를 사용하세요.")
        return 0
    for target in targets:
        try:
            run_one(target.id, args)
        except (OperationalError, ValueError) as exc:
            print(f"실패: {target.title} | {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
