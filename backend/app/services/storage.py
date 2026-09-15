import hashlib
from collections.abc import Iterator

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import Settings


class PrivateStorage:
    """Private S3-compatible storage. Object keys never leave admin API responses."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.s3_bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.settings.s3_bucket)

    def create_upload_url(self, object_key: str, sha256: str) -> str:
        self.ensure_bucket()
        return self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket,
                "Key": object_key,
                "ContentType": "application/pdf",
                "Metadata": {"sha256": sha256},
            },
            ExpiresIn=self.settings.upload_url_ttl_seconds,
            HttpMethod="PUT",
        )

    def validate_pdf(self, object_key: str, expected_size: int, expected_sha256: str) -> int:
        """Verify storage metadata and content before moving the manual to UPLOADED."""
        from fitz import open as open_pdf

        head = self.client.head_object(Bucket=self.settings.s3_bucket, Key=object_key)
        content_type = (head.get("ContentType") or "").split(";", 1)[0].lower()
        stored_hash = (head.get("Metadata") or {}).get("sha256", "").lower()
        if head.get("ContentLength") != expected_size or content_type != "application/pdf":
            raise ValueError("업로드한 파일의 크기 또는 형식이 올바르지 않습니다.")
        if stored_hash != expected_sha256.lower():
            raise ValueError("업로드한 파일의 해시가 일치하지 않습니다.")

        body = self.client.get_object(Bucket=self.settings.s3_bucket, Key=object_key)["Body"]
        content = b"".join(_read_chunks(body))
        if hashlib.sha256(content).hexdigest().lower() != expected_sha256.lower():
            raise ValueError("업로드한 파일의 해시가 일치하지 않습니다.")
        try:
            document = open_pdf(stream=content, filetype="pdf")
            page_count = document.page_count
            document.close()
        except Exception as exc:  # PyMuPDF normalizes malformed PDF errors poorly.
            raise ValueError("유효한 PDF 파일이 아닙니다.") from exc
        if page_count < 1:
            raise ValueError("페이지가 없는 PDF 파일은 업로드할 수 없습니다.")
        return page_count

    def read_bytes(self, object_key: str) -> bytes:
        """Read a private object for server-side ingestion only."""
        body = self.client.get_object(Bucket=self.settings.s3_bucket, Key=object_key)["Body"]
        return b"".join(_read_chunks(body))

    def create_download_url(self, object_key: str) -> str:
        """Create a short-lived URL without exposing storage details in API data."""
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.s3_bucket, "Key": object_key},
            ExpiresIn=self.settings.upload_url_ttl_seconds,
            HttpMethod="GET",
        )


def _read_chunks(body: object) -> Iterator[bytes]:
    while True:
        chunk = body.read(1024 * 1024)  # type: ignore[attr-defined]
        if not chunk:
            return
        yield chunk
