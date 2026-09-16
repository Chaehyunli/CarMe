"""Small, explicit Ollama embedding client used by ingestion and retrieval."""

from collections.abc import Sequence

import httpx

from app.core.config import Settings, get_settings


class EmbeddingError(RuntimeError):
    """The configured embedding model did not return a usable vector."""


def embed_texts(texts: Sequence[str], settings: Settings | None = None) -> list[list[float]]:
    """Embed a batch through Ollama and validate its contract strictly.

    Ollama's ``/api/embed`` endpoint accepts many inputs at once.  Validation
    here prevents a configuration/model-dimension mismatch from being stored
    in pgvector and discovered only after the manual has been published.
    """

    if not texts:
        return []
    runtime = settings or get_settings()
    try:
        with httpx.Client(timeout=runtime.embedding_timeout_seconds) as client:
            response = client.post(
                f"{runtime.ollama_base_url.rstrip('/')}/api/embed",
                json={
                    "model": runtime.ollama_embedding_model,
                    "input": list(texts),
                    "truncate": True,
                    "keep_alive": "30m",
                },
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise EmbeddingError("Ollama 임베딩 모델을 호출하지 못했습니다.") from exc

    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise EmbeddingError("Ollama 임베딩 응답 개수가 입력과 일치하지 않습니다.")
    vectors: list[list[float]] = []
    for vector in embeddings:
        if not isinstance(vector, list) or len(vector) != runtime.embedding_dimensions:
            actual = len(vector) if isinstance(vector, list) else 0
            raise EmbeddingError(
                f"임베딩 차원이 맞지 않습니다. 설정 {runtime.embedding_dimensions}, 응답 {actual}."
            )
        try:
            vectors.append([float(value) for value in vector])
        except (TypeError, ValueError) as exc:
            raise EmbeddingError("Ollama 임베딩 응답에 숫자가 아닌 값이 있습니다.") from exc
    return vectors


def embed_text(text: str, settings: Settings | None = None) -> list[float]:
    return embed_texts([text], settings)[0]
