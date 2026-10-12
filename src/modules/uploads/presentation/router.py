from fastapi import APIRouter, Depends, File, UploadFile, status

from src.app.database.models import UserModel
from src.modules.auth.presentation.dependencies import get_current_user
from src.modules.uploads.application.services import SecureUploadService

uploads_router = APIRouter(prefix="/uploads", tags=["File Uploads"])
upload_service = SecureUploadService()


@uploads_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Securely upload an image or financial document attachment",
)
@uploads_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def upload_attachment(
    file: UploadFile = File(..., description="Multipart file attachment"),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """Validate, sanitize, and persist file with collision-resistant naming under a strict extension whitelist."""
    return await upload_service.save_file(file)
