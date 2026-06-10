import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.agents.invoices.ai_extractor import refine_metadata_with_ai
from backend.agents.invoices.extractor import InvoiceMetadata, extract_metadata
from backend.agents.invoices.scanner import _should_archive, _should_ignore_document, InvoiceAgentConfig


class FakeLlmClient:
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_with_file(self, path: str, prompt: str, system: str):
        return SimpleNamespace(text=json.dumps(self.payload))


class InvoiceDocumentClassificationTest(unittest.TestCase):
    def _base_metadata(self) -> InvoiceMetadata:
        return InvoiceMetadata(
            source_path="steuerbescheid.pdf",
            file_hash="hash",
            is_invoice=False,
            confidence=0.3,
            vendor="Finanzamt",
            invoice_date=__import__("datetime").date(2026, 6, 1),
            amount=1200.0,
            currency="EUR",
            invoice_number="",
            category="Unsortiert",
            reason="test",
            document_type="document",
            transaction_type="expense",
            gross_amount=1200.0,
            review_status="needs_review",
        )

    def test_tax_assessment_refund_is_income_and_needs_review(self):
        metadata = refine_metadata_with_ai(
            path=Path("steuerbescheid.pdf"),
            metadata=self._base_metadata(),
            llm_client=FakeLlmClient({
                "document_type": "Steuerbescheid",
                "is_invoice": True,
                "transaction_type": "expense",
                "vendor": "Finanzamt",
                "invoice_date": "2026-06-01",
                "gross_amount": "1.200,00",
                "currency": "EUR",
                "category": "Steuer",
                "is_business": False,
                "is_tax_relevant": True,
                "confidence": 0.96,
                "reason": "Einkommensteuerbescheid mit Erstattung und Guthaben",
            }),
            default_category="Unsortiert",
        )

        self.assertTrue(metadata.is_invoice)
        self.assertEqual(metadata.document_type, "assessment")
        self.assertEqual(metadata.transaction_type, "income")
        self.assertEqual(metadata.category, "Steuer")
        self.assertEqual(metadata.gross_amount, 1200.0)
        self.assertEqual(metadata.review_status, "needs_review")

    def test_offer_is_not_accounting_document(self):
        metadata = refine_metadata_with_ai(
            path=Path("angebot.pdf"),
            metadata=self._base_metadata(),
            llm_client=FakeLlmClient({
                "document_type": "Angebot",
                "is_invoice": False,
                "transaction_type": "expense",
                "vendor": "Muster GmbH",
                "invoice_date": "2026-06-01",
                "gross_amount": "999,00",
                "currency": "EUR",
                "category": "Unsortiert",
                "is_business": True,
                "is_tax_relevant": False,
                "confidence": 0.98,
                "reason": "Angebot ohne Zahlungspflicht",
            }),
            default_category="Unsortiert",
        )

        self.assertFalse(metadata.is_invoice)
        self.assertEqual(metadata.document_type, "offer")
        self.assertEqual(metadata.category, "Nicht relevant")
        self.assertTrue(_should_ignore_document(metadata))

    def test_local_extractor_rejects_flyer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "werbe_flyer.txt"
            path.write_text("Großer Prospekt und Flyer mit Preisliste, aber keine Rechnung.", encoding="utf-8")
            metadata = extract_metadata(path)

        self.assertFalse(metadata.is_invoice)
        self.assertEqual(metadata.document_type, "advertisement")
        self.assertTrue(_should_ignore_document(metadata))

    def test_assessment_is_not_auto_archived(self):
        metadata = self._base_metadata()
        metadata.document_type = "assessment"
        metadata.is_invoice = True
        metadata.confidence = 0.99
        metadata.amount = 500.0
        config = InvoiceAgentConfig(
            inbox_dir=Path("inbox"),
            archive_dir=Path("archive"),
            review_dir=Path("review"),
            database_path=Path("db.sqlite"),
            email_attachment_dir=Path("inbox"),
            archive_cleanup_backup_dir=Path("backup"),
            poll_interval_seconds=600,
            confidence_threshold=0.5,
            require_amount_for_archive=True,
        )

        self.assertFalse(_should_archive(config, metadata))
        self.assertFalse(_should_ignore_document(metadata))

class InvoiceServiceAccountingViewTest(unittest.TestCase):
    def test_month_view_excludes_not_relevant_and_uses_assessment_refund_amount(self):
        import tempfile
        from backend.agents.invoices.service import InvoiceService

        with tempfile.TemporaryDirectory() as tmp:
            service = InvoiceService.__new__(InvoiceService)
            root = Path(tmp)
            service.database_path = root / "invoices.db"
            service.inbox_dir = root / "inbox"
            service.archive_dir = root / "archive"
            service.review_dir = root / "review"
            service.export_dir = root / "exports"
            service.archive_cleanup_backup_dir = root / "backup"
            service.run_lock = None
            service.scheduler_stop = None
            service.scheduler_thread = None
            service._ensure_schema()

            with service.connect() as connection:
                connection.execute(
                    """
                    insert into invoices (
                        file_hash, source_path, archive_path, is_invoice, confidence, vendor,
                        invoice_date, amount, currency, invoice_number, category, status,
                        reason, document_type, transaction_type, year, month, gross_amount,
                        open_amount, review_status, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "offer", "angebot.pdf", "review/angebot.pdf", 1, 0.95, "Muster GmbH",
                        "2026-06-01", 999.0, "EUR", "", "Nicht relevant", "review",
                        "angebot", "offer", "expense", 2026, 6, 999.0,
                        None, "needs_review", "2026-06-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00",
                    ),
                )
                connection.execute(
                    """
                    insert into invoices (
                        file_hash, source_path, archive_path, is_invoice, confidence, vendor,
                        invoice_date, amount, currency, invoice_number, category, status,
                        reason, document_type, transaction_type, year, month, gross_amount,
                        open_amount, review_status, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "tax", "steuerbescheid.pdf", "review/steuerbescheid.pdf", 1, 0.95, "Finanzamt",
                        "2026-06-02", 5000.0, "EUR", "", "Steuer", "review",
                        "erstattung", "assessment", "income", 2026, 6, 5000.0,
                        320.0, "needs_review", "2026-06-02T00:00:00+00:00", "2026-06-02T00:00:00+00:00",
                    ),
                )
                connection.commit()

            month = service.month(2026, 6, {})
            year = service.year(2026)
            years = service.years()

        self.assertEqual(len(month["invoices"]), 1)
        self.assertEqual(month["invoices"][0]["document_type"], "assessment")
        self.assertEqual(year["months"][5]["income_total"], 320.0)
        self.assertEqual(year["months"][5]["expense_total"], 0)
        self.assertEqual(years[0]["income_total"], 320.0)
        self.assertEqual(years[0]["expense_total"], 0)

class InvoiceEbonUploadTest(unittest.TestCase):
    def test_ebon_upload_writes_text_file_to_inbox(self):
        import tempfile
        from backend.agents.invoices.service import InvoiceService

        with tempfile.TemporaryDirectory() as tmp:
            service = InvoiceService.__new__(InvoiceService)
            root = Path(tmp)
            service.inbox_dir = root / "inbox"
            result = service.upload_ebon_content(
                content='{"merchant":"Baeckerei","total":"4,20 EUR"}',
                filename="baeckerei-bon.qr",
                source="test_qr",
            )
            stored = Path(result["path"])
            text = stored.read_text(encoding="utf-8")

        self.assertEqual(result["type"], "ebon_qr")
        self.assertEqual(stored.suffix, ".txt")
        self.assertIn("source: test_qr", text)
        self.assertIn('"merchant":"Baeckerei"', text)

    def test_txt_ebon_is_ai_extractable_when_configured(self):
        from backend.agents.invoices.extractor import InvoiceMetadata
        from backend.agents.invoices.scanner import AIExtractionConfig, InvoiceAgentConfig, _should_use_ai_extraction
        from datetime import date

        metadata = InvoiceMetadata(
            source_path="e-bon.txt",
            file_hash="hash",
            is_invoice=False,
            confidence=0.2,
            vendor="Unbekannt",
            invoice_date=date(2026, 6, 10),
            amount=None,
            currency="EUR",
            invoice_number="",
            category="Unsortiert",
            reason="test",
            document_type="document",
        )
        config = InvoiceAgentConfig(
            inbox_dir=Path("inbox"),
            archive_dir=Path("archive"),
            review_dir=Path("review"),
            database_path=Path("db.sqlite"),
            email_attachment_dir=Path("inbox"),
            archive_cleanup_backup_dir=Path("backup"),
            poll_interval_seconds=600,
            ai_extraction=AIExtractionConfig(enabled=True, always_for_documents=True),
        )

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "e-bon.txt"
            path.write_text("merchant=Baeckerei\ntotal=4,20 EUR", encoding="utf-8")
            self.assertTrue(_should_use_ai_extraction(config, metadata, path))

class PrivateConsumerReceiptTests(unittest.TestCase):
    def test_rewe_receipt_is_private_and_not_tax_relevant_even_if_ai_claims_business(self):
        metadata = InvoiceMetadata(
            source_path="rewe-bon.txt",
            file_hash="hash",
            is_invoice=True,
            confidence=0.6,
            vendor="REWE",
            invoice_date=__import__("datetime").date(2026, 6, 10),
            amount=23.45,
            currency="EUR",
            invoice_number="",
            category="Unsortiert",
            reason="test",
            document_type="receipt",
            transaction_type="expense",
            gross_amount=23.45,
            is_business=True,
            is_tax_relevant=True,
        )

        refined = refine_metadata_with_ai(
            path=Path("rewe-bon.txt"),
            metadata=metadata,
            llm_client=FakeLlmClient({
                "document_type": "receipt",
                "is_invoice": True,
                "transaction_type": "expense",
                "vendor": "REWE Markt GmbH",
                "invoice_date": "2026-06-10",
                "gross_amount": "23,45",
                "currency": "EUR",
                "category": "Lebensmittel",
                "is_business": True,
                "is_tax_relevant": True,
                "confidence": 0.95,
                "reason": "Kassenbon REWE",
            }),
            default_category="Unsortiert",
        )

        self.assertTrue(refined.is_invoice)
        self.assertEqual(refined.document_type, "receipt")
        self.assertFalse(refined.is_business)
        self.assertFalse(refined.is_tax_relevant)
        self.assertEqual(refined.category, "Lebensmittel")

    def test_local_rewe_receipt_is_private_and_not_tax_relevant(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rewe_kassenbon.txt"
            path.write_text("REWE Markt Kassenbon\nGesamtbetrag 23,45 EUR\nVielen Dank", encoding="utf-8")
            metadata = extract_metadata(path)

        self.assertTrue(metadata.is_invoice)
        self.assertEqual(metadata.category, "Lebensmittel")
        self.assertFalse(metadata.is_business)
        self.assertFalse(metadata.is_tax_relevant)

    def test_month_view_includes_private_not_tax_relevant_receipt(self):
        import tempfile
        from backend.agents.invoices.service import InvoiceService

        with tempfile.TemporaryDirectory() as tmp:
            service = InvoiceService.__new__(InvoiceService)
            root = Path(tmp)
            service.database_path = root / "invoices.db"
            service.inbox_dir = root / "inbox"
            service.archive_dir = root / "archive"
            service.review_dir = root / "review"
            service.export_dir = root / "exports"
            service.archive_cleanup_backup_dir = root / "backup"
            service._ensure_schema()

            with service.connect() as connection:
                connection.execute(
                    """
                    insert into invoices (
                        file_hash, source_path, archive_path, is_invoice, confidence, vendor,
                        invoice_date, amount, currency, invoice_number, category, status,
                        reason, document_type, transaction_type, year, month, gross_amount,
                        is_business, is_tax_relevant, review_status, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "rewe", "rewe.txt", "archive/rewe.txt", 1, 0.95, "REWE",
                        "2026-06-10", 23.45, "EUR", "", "Lebensmittel", "archived",
                        "private receipt", "receipt", "expense", 2026, 6, 23.45,
                        0, 0, "reviewed", "2026-06-10T00:00:00+00:00", "2026-06-10T00:00:00+00:00",
                    ),
                )
                connection.commit()

            month = service.month(2026, 6, {})
            year = service.year(2026)

        self.assertEqual(len(month["invoices"]), 1)
        self.assertEqual(month["invoices"][0]["vendor"], "REWE")
        self.assertEqual(year["months"][5]["expense_total"], 23.45)

    def test_tax_export_excludes_private_not_tax_relevant_receipt(self):
        import tempfile
        from backend.agents.invoices.tax_export import _load_invoice_rows
        from backend.agents.invoices.service import InvoiceService

        with tempfile.TemporaryDirectory() as tmp:
            service = InvoiceService.__new__(InvoiceService)
            root = Path(tmp)
            service.database_path = root / "invoices.db"
            service.inbox_dir = root / "inbox"
            service.archive_dir = root / "archive"
            service.review_dir = root / "review"
            service.export_dir = root / "exports"
            service.archive_cleanup_backup_dir = root / "backup"
            service._ensure_schema()

            with service.connect() as connection:
                connection.execute(
                    """
                    insert into invoices (
                        file_hash, source_path, archive_path, is_invoice, confidence, vendor,
                        invoice_date, amount, currency, invoice_number, category, status,
                        reason, document_type, transaction_type, year, month, gross_amount,
                        is_business, is_tax_relevant, review_status, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "rewe", "rewe.txt", "archive/rewe.txt", 1, 0.95, "REWE",
                        "2026-06-10", 23.45, "EUR", "", "Lebensmittel", "archived",
                        "private receipt", "receipt", "expense", 2026, 6, 23.45,
                        0, 0, "reviewed", "2026-06-10T00:00:00+00:00", "2026-06-10T00:00:00+00:00",
                    ),
                )
                connection.commit()

            rows = _load_invoice_rows(service.database_path, 2026)

        self.assertEqual(rows, [])

if __name__ == "__main__":
    unittest.main()

