import mimetypes
from fastapi.responses import FileResponse
from typing import Optional

from backend.invoice.service import InvoiceService


class FileService:
    def __init__(self, invoice_service: Optional[InvoiceService] = None):
        self.invoice_service = invoice_service or InvoiceService()

    def document_response(self, invoice_id: int) -> FileResponse:
        path = self.invoice_service.document_path(invoice_id)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(
            path,
            filename=path.name,
            media_type=media_type,
            content_disposition_type="inline",
        )
