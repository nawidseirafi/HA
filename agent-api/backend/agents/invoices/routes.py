from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .export_service import ExportService
from .file_service import FileService
from .service import InvoiceService


router = APIRouter(prefix="/api/invoices", tags=["invoices"])
invoice_service = InvoiceService()
file_service = FileService(invoice_service)
export_service = ExportService(invoice_service)


class InvoiceAgentSettingsPayload(BaseModel):
    enabled: Optional[bool] = None
    schedule: Optional[list[str]] = None


class EBonUploadPayload(BaseModel):
    content: str
    filename: Optional[str] = None
    source: Optional[str] = None


class ContractPayload(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    monthly_cost: Optional[float] = None
    annual_cost: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    renewal_date: Optional[str] = None
    cancellation_period: Optional[str] = None
    auto_renew: Optional[bool] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    document_id: Optional[int] = None


@router.get("/summary")
def invoice_summary():
    return invoice_service.summary()


@router.get("/finance/summary")
def finance_summary():
    return invoice_service.finance_summary()


@router.get("/agent/status")
def invoice_agent_status():
    return invoice_service.status()


@router.post("/agent/enable")
def enable_invoice_agent():
    return invoice_service.enable()


@router.post("/agent/disable")
def disable_invoice_agent():
    return invoice_service.disable()


@router.post("/agent/toggle")
def toggle_invoice_agent():
    return invoice_service.toggle()


@router.put("/agent/settings")
def update_invoice_agent_settings(payload: InvoiceAgentSettingsPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return invoice_service.update_agent_settings(data)


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


@router.get("/contracts")
def list_contracts(
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    return {"contracts": invoice_service.contracts({"category": category, "status": status, "search": search})}


@router.post("/contracts")
def create_contract(payload: ContractPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return invoice_service.create_contract(data)


@router.get("/contracts/analysis")
def contract_analysis():
    return invoice_service.contract_analysis()


@router.get("/contracts/reminders")
def contract_reminders():
    return {"reminders": invoice_service.contract_reminders()}


@router.get("/contracts/{contract_id}")
def contract_detail(contract_id: int):
    return invoice_service.get_contract(contract_id)


@router.put("/contracts/{contract_id}")
def update_contract(contract_id: int, payload: ContractPayload):
    data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
    return invoice_service.update_contract(contract_id, data)


@router.delete("/contracts/{contract_id}")
def delete_contract(contract_id: int):
    return invoice_service.delete_contract(contract_id)


@router.post("/{invoice_id}/create-contract")
def create_contract_from_invoice(invoice_id: int):
    return invoice_service.analyze_invoice_as_contract(invoice_id)


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


@router.post("/upload/contract")
def upload_contract_document(file: UploadFile = File(...)):
    return invoice_service.upload_contract_document(file)


@router.post("/upload/ebon")
def upload_ebon(payload: EBonUploadPayload):
    return invoice_service.upload_ebon_content(
        content=payload.content,
        filename=payload.filename,
        source=payload.source,
    )


@router.post("/run")
def run_invoice_agent():
    return invoice_service.run_agent()


@router.post("/cleanup-archive")
def cleanup_invoice_archive(apply: bool = Query(False)):
    return invoice_service.cleanup_archive(apply=apply)
