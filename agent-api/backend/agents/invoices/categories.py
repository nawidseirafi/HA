import re
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from invoices.extractor import InvoiceMetadata


def apply_category_rules(
    metadata: InvoiceMetadata,
    category_rules: Optional[dict[str, str]],
    default_category: str,
) -> InvoiceMetadata:
    category, keyword = category_for_values(
        {
            "vendor": metadata.vendor,
            "source_path": metadata.source_path,
            "invoice_number": metadata.invoice_number,
            "category": metadata.category,
        },
        category_rules,
    )
    if not category:
        return metadata
    if category == metadata.category:
        return metadata
    reason = metadata.reason or ""
    suffix = f"category_rule:{keyword}"
    if suffix not in reason:
        reason = f"{reason}; {suffix}" if reason else suffix
    return replace(metadata, category=category or default_category, reason=reason)


def category_for_values(values: dict[str, Any], category_rules: Optional[dict[str, str]]) -> tuple[str, str]:
    if not category_rules:
        return "", ""
    text = " ".join(str(value or "") for value in values.values()).lower()
    matched = [
        (keyword, category)
        for keyword, category in category_rules.items()
        if _keyword_matches(keyword, text)
    ]
    if not matched:
        return "", ""
    keyword, category = max(matched, key=lambda item: len(item[0]))
    return category, keyword


def refresh_database_categories(
    database_path: Path,
    category_rules: dict[str, str],
) -> int:
    if not database_path.exists():
        return 0
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    changed = 0
    try:
        rows = connection.execute(
            """
            select id, vendor, source_path, archive_path, invoice_number, category, reason
            from invoices
            """
        ).fetchall()
        for row in rows:
            category, keyword = category_for_values(
                {
                    "vendor": row["vendor"],
                    "source_path": row["source_path"],
                    "archive_path": row["archive_path"],
                    "invoice_number": row["invoice_number"],
                    "category": row["category"],
                },
                category_rules,
            )
            if not category or category == row["category"]:
                continue
            reason = row["reason"] or ""
            suffix = f"category_rule:{keyword}"
            if suffix not in reason:
                reason = f"{reason}; {suffix}" if reason else suffix
            connection.execute(
                "update invoices set category = ?, reason = ? where id = ?",
                (category, reason, row["id"]),
            )
            changed += 1
        connection.commit()
    finally:
        connection.close()
    return changed


def _keyword_matches(keyword: str, text: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])", text))
