"""Optional local-LLM answer-format checks for grounded RAG evidence.

The main corpus evaluation is deterministic and validates retrieval plus the
evidence gate.  These checks are intentionally separate because natural
language generation can vary by the installed local chat model.
"""

from __future__ import annotations

import os

import pytest

from app.db.models import OfficialSource
from app.services.chat_sessions import grounded_answer

from .test_local_corpus_quality import SCENARIOS, run_scenario

pytestmark = pytest.mark.skipif(
    os.getenv("CARME_RUN_RAG_LLM_EVAL") != "1",
    reason="Set CARME_RUN_RAG_LLM_EVAL=1 after pulling the local chat model.",
)


@pytest.mark.rag_llm_evaluation
@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_id", ["AVN-WEB-001", "SON-PDF-001"])
async def test_grounded_answer_is_user_facing_and_not_a_raw_excerpt(scenario_id: str) -> None:
    scenario = next(item for item in SCENARIOS if item.id == scenario_id)
    result = run_scenario(scenario)
    assert result.decision.hits

    answer = await grounded_answer(
        scenario.question,
        [hit.chunk for hit in result.decision.hits],
        list(scenario.history),
        result.decision.result_status,
    )

    assert len(answer.strip()) >= 12
    assert "PDF " not in answer
    assert "매뉴얼 근거" not in answer
    assert not any(phrase in answer for phrase in ("확실히 고장", "반드시 교체", "원인은 냉매"))
    if "방법" in scenario.question or "어떻게" in scenario.question:
        assert "방법" in answer
        assert any(f"{number}." in answer for number in range(1, 6))
    # The answer must still represent the selected evidence domain, rather
    # than copying a random unrelated section into a fluent response.
    if isinstance(result.top_hit.chunk, OfficialSource):
        assert "블루투스" in answer
