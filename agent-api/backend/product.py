from __future__ import annotations

from dataclasses import dataclass


PRODUCT_ID = "robotersteve"
PRODUCT_NAME = "RoboterSteve"


@dataclass(frozen=True)
class ProductInfo:
    id: str = PRODUCT_ID
    name: str = PRODUCT_NAME
    description: str = "RoboterSteve"
    frontend_app: str = "personal"

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "frontend_app": self.frontend_app,
        }


def active_product() -> ProductInfo:
    return ProductInfo()


def is_core_service_enabled(service_id: str) -> bool:
    return bool(str(service_id or "").strip())
