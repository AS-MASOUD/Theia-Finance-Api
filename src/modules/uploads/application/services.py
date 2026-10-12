import os
from pathlib import Path
import re
import uuid

from fastapi import HTTPException, UploadFile

from src.app.core.exceptions import AppException

# Strict whitelist of permitted file extensions
ALLOWED_EXTENSIONS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".pdf",
    ".csv",
    ".xlsx",
}

# Explicit blacklist of dangerous and active file extensions (defense-in-depth)
DANGEROUS_EXTENSIONS: set[str] = {
    ".exe",
    ".dll",
    ".bat",
    ".sh",
    ".php",
    ".asp",
    ".aspx",
    ".jsp",
    ".html",
    ".htm",
    ".svg",
    ".cgi",
    ".cmd",
    ".vbs",
    ".ps1",
    ".jar",
    ".war",
    ".py",
    ".rb",
    ".pl",
    ".phtml",
    ".phar",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
UPLOAD_DIR = Path("uploads")


class SecureUploadService:
    def __init__(self, target_dir: Path | None = None):
        self.upload_dir = target_dir or UPLOAD_DIR
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def validate_and_sanitize_filename(self, filename: str | None) -> tuple[str, str]:
        """Sanitize original filename and extract validated extension.
        
        Rejects files missing extensions, containing directory traversal,
        or matching dangerous executable/script formats.
        """
        if not filename or not filename.strip():
            raise AppException(
                "Uploaded file must have a valid filename.",
                code="INVALID_FILENAME",
                status_code=400,
            )

        # Extract only the base name (prevents directory traversal attacks)
        safe_base = Path(filename).name
        # Remove any null bytes or non-printable chars
        safe_base = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", safe_base).strip()

        # Extract extension (case-insensitive)
        ext = Path(safe_base).suffix.lower()
        if not ext:
            raise AppException(
                "Files without an extension are prohibited.",
                code="MISSING_FILE_EXTENSION",
                status_code=400,
            )

        if ext in DANGEROUS_EXTENSIONS:
            raise AppException(
                f"File extension '{ext}' is considered dangerous and strictly blocked.",
                code="DANGEROUS_FILE_EXTENSION",
                status_code=400,
            )

        if ext not in ALLOWED_EXTENSIONS:
            allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise AppException(
                f"File extension '{ext}' is not permitted. Allowed extensions: {allowed_list}",
                code="UNSUPPORTED_FILE_EXTENSION",
                status_code=400,
            )

        return safe_base, ext

    async def save_file(self, file: UploadFile) -> dict[str, str | int]:
        """Securely validate, read, and write uploaded file using collision-resistant naming."""
        safe_original_name, ext = self.validate_and_sanitize_filename(file.filename)

        content = await file.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise AppException(
                f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
                code="FILE_TOO_LARGE",
                status_code=413,
            )

        # Generate collision-resistant GUID filename
        file_uuid = uuid.uuid4().hex
        stored_filename = f"{file_uuid}{ext}"
        target_path = self.upload_dir / stored_filename

        with open(target_path, "wb") as f:
            f.write(content)

        return {
            "id": file_uuid,
            "stored_filename": stored_filename,
            "original_filename": safe_original_name,
            "extension": ext,
            "size_bytes": len(content),
            "content_type": file.content_type or "application/octet-stream",
            "url": f"/uploads/{stored_filename}",
        }
