from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse

from backend.agents.invoices.export_service import ExportService
from backend.agents.invoices.file_service import FileService
from backend.agents.invoices.service import InvoiceService


router = APIRouter(prefix="/api/invoices", tags=["invoices"])
invoice_service = InvoiceService()
file_service = FileService(invoice_service)
export_service = ExportService(invoice_service)


@router.get("/summary")
def invoice_summary():
    return invoice_service.summary()


@router.get("/years")
def invoice_years():
    return {"years": invoice_service.years()}


@router.get("/years/{year}")
def invoice_year(year: int):
    return invoice_service.year(year)


@router.get("/years/{year}/months/{month}")
def invoice_month(
    year: int,
    month: int,
    category: Optional[str] = None,
    status: Optional[str] = None,
    vendor: Optional[str] = None,
    amount_min: Optional[float] = Query(None, alias="amountMin"),
    amount_max: Optional[float] = Query(None, alias="amountMax"),
    search: Optional[str] = None,
):
    return invoice_service.month(
        year,
        month,
        {
            "category": category,
            "status": status,
            "vendor": vendor,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "search": search,
        },
    )


@router.get("/exports/year/{year}/excel")
def export_year_excel(year: int) -> FileResponse:
    path = export_service.excel(year)
    return FileResponse(path, filename=path.name)


@router.get("/exports/year/{year}/pdf")
def export_year_pdf(year: int) -> FileResponse:
    path = export_service.pdf_summary(year)
    return FileResponse(path, filename=path.name)


@router.get("/exports/year/{year}/zip")
def export_year_zip(year: int) -> FileResponse:
    path = export_service.zip_documents(year)
    return FileResponse(path, filename=path.name)


@router.get("/exports/month/{year}/{month}/excel")
def export_month_excel(year: int, month: int) -> FileResponse:
    path = export_service.excel(year, month)
    return FileResponse(path, filename=path.name)


@router.get("/exports/month/{year}/{month}/pdf")
def export_month_pdf(year: int, month: int) -> FileResponse:
    path = export_service.pdf_summary(year, month)
    return FileResponse(path, filename=path.name)


@router.get("/exports/month/{year}/{month}/zip")
def export_month_zip(year: int, month: int) -> FileResponse:
    path = export_service.zip_documents(year, month)
    return FileResponse(path, filename=path.name)


@router.get("/{invoice_id}")
def invoice_detail(invoice_id: int):
    return invoice_service.get(invoice_id)


@router.get("/{invoice_id}/file")
def invoice_file(invoice_id: int) -> FileResponse:
    return file_service.document_response(invoice_id)


@router.put("/{invoice_id}")
def update_invoice(invoice_id: int, payload: dict):
    return invoice_service.update(invoice_id, payload)


@router.post("/{invoice_id}/reanalyze")
def reanalyze_invoice(invoice_id: int):
    return invoice_service.reanalyze(invoice_id)


@router.post("/{invoice_id}/mark-reviewed")
def mark_reviewed(invoice_id: int):
    return invoice_service.mark_reviewed(invoice_id)


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int):
    return invoice_service.delete(invoice_id)


@router.post("/upload")
def upload_invoice(file: UploadFile = File(...)):
    return invoice_service.upload(file)


@router.post("/run")
def run_invoice_agent():
    return invoice_service.run_agent()
