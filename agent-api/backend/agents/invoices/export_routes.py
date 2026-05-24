from fastapi import APIRouter
from fastapi.responses import FileResponse

from backend.agents.invoices.export_service import ExportService


router = APIRouter(prefix="/api/exports", tags=["exports"])
export_service = ExportService()


@router.get("/year/{year}/excel")
def export_year_excel(year: int) -> FileResponse:
    path = export_service.excel(year)
    return FileResponse(path, filename=path.name)


@router.get("/year/{year}/pdf")
def export_year_pdf(year: int) -> FileResponse:
    path = export_service.pdf_summary(year)
    return FileResponse(path, filename=path.name)


@router.get("/year/{year}/zip")
def export_year_zip(year: int) -> FileResponse:
    path = export_service.zip_documents(year)
    return FileResponse(path, filename=path.name)


@router.get("/month/{year}/{month}/excel")
def export_month_excel(year: int, month: int) -> FileResponse:
    path = export_service.excel(year, month)
    return FileResponse(path, filename=path.name)


@router.get("/month/{year}/{month}/pdf")
def export_month_pdf(year: int, month: int) -> FileResponse:
    path = export_service.pdf_summary(year, month)
    return FileResponse(path, filename=path.name)


@router.get("/month/{year}/{month}/zip")
def export_month_zip(year: int, month: int) -> FileResponse:
    path = export_service.zip_documents(year, month)
    return FileResponse(path, filename=path.name)
