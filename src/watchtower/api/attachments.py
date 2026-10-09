"""Bounded multipart reader shared by CMS and attachment API."""
from starlette.datastructures import FormData, UploadFile

from watchtower.services.attachments import MAX_ATTACHMENT_BYTES, AttachmentUpload
from watchtower.services.workspace import ServiceError


async def read_uploads(form: FormData) -> list[AttachmentUpload]:
    uploads = []
    total = 0
    for value in form.getlist("context_files"):
        if not isinstance(value, UploadFile) or not value.filename:
            continue
        try:
            content = await value.read(MAX_ATTACHMENT_BYTES + 1)
        finally:
            await value.close()
        total += len(content)
        if len(uploads) >= 20 or total > 100 * 1024 * 1024 or len(content) > MAX_ATTACHMENT_BYTES:
            raise ServiceError("Attach at most 20 files, up to 20 MB each and 100 MB per save.")
        uploads.append(AttachmentUpload(value.filename, content))
    return uploads
