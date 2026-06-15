from datetime import date
from pathlib import Path

from backend.agents.invoices.service import InvoiceService


def _service(tmp_path: Path) -> InvoiceService:
    service = InvoiceService.__new__(InvoiceService)
    service.database_path = tmp_path / "invoices.db"
    service.inbox_dir = tmp_path / "inbox"
    service.archive_dir = tmp_path / "archive"
    service.review_dir = tmp_path / "review"
    service.export_dir = tmp_path / "exports"
    service.archive_cleanup_backup_dir = tmp_path / "backup"
    service.run_lock = None
    service.scheduler_stop = None
    service.scheduler_thread = None
    service._ensure_schema()
    return service


def _monthly_contract() -> dict:
    return {
        "id": 1,
        "name": "MAINGAU Energie GmbH",
        "provider": "MAINGAU Energie GmbH",
        "category": "energy",
        "subcategory": "Strom",
        "status": "needs_review",
        "start_date": "2023-07-11",
        "end_date": "2026-06-15",
        "renewal_date": "2026-07-11",
        "cancellation_period": "1 Monat",
        "notes": "monatlich kündbar",
    }


def test_monthly_cancellable_contract_uses_today_plus_one_month_on_2026_06_15(tmp_path):
    service = _service(tmp_path)

    info = service._contract_deadline_info(_monthly_contract(), today=date(2026, 6, 15))

    assert info["deadline"] == "2026-07-15"
    assert info["days_left"] == 30
    assert info["rolling"] is True
    assert info["overdue"] is False


def test_monthly_cancellable_contract_uses_today_plus_one_month_on_2026_06_16(tmp_path):
    service = _service(tmp_path)

    info = service._contract_deadline_info(_monthly_contract(), today=date(2026, 6, 16))

    assert info["deadline"] == "2026-07-16"
    assert info["days_left"] == 30
    assert info["rolling"] is True
    assert info["overdue"] is False


def test_monthly_cancellable_contract_is_not_overdue_even_with_old_fixed_deadline(tmp_path):
    service = _service(tmp_path)

    info = service._contract_deadline_info(_monthly_contract(), today=date(2026, 6, 17))

    assert info["deadline"] == "2026-07-17"
    assert info["days_left"] == 30
    assert info["overdue"] is False


def test_contract_detail_and_dashboard_use_same_next_cancellation_value(tmp_path):
    service = _service(tmp_path)
    contract = service.create_contract(
        {
            "name": "MAINGAU Energie GmbH",
            "provider": "MAINGAU Energie GmbH",
            "category": "energy",
            "subcategory": "Strom",
            "monthly_cost": 150.0,
            "start_date": "2023-07-11",
            "end_date": "2026-06-15",
            "renewal_date": "2026-07-11",
            "cancellation_period": "1 Monat",
            "status": "needs_review",
            "notes": "monatlich kündbar",
        }
    )
    dashboard_next = service._next_contract_deadline([contract])

    assert contract["next_cancellation"]["deadline"] == dashboard_next["deadline"]
    assert contract["next_cancellation"]["rolling"] is True
    assert dashboard_next["rolling"] is True
