from dataclasses import dataclass
from decimal import Decimal

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.repositories.system import SysConfigRepository


@dataclass(frozen=True)
class ProductPolicy:
    product_type: str
    product_name: str
    amount: Decimal
    points: int
    first_purchase_only: bool = False


class ProductPolicyService:
    def __init__(self, config_repo: SysConfigRepository) -> None:
        self.config_repo = config_repo

    def get_policy(self, product_type: str) -> ProductPolicy:
        normalized = (product_type or "").strip().upper()
        settings = get_settings()
        defaults = {
            "FIRST_RECHARGE_GIFT": ProductPolicy(
                product_type="FIRST_RECHARGE_GIFT",
                product_name="首充礼包",
                amount=Decimal(settings.first_recharge_gift_amount),
                points=settings.first_recharge_gift_points,
                first_purchase_only=True,
            ),
            "POINT_PACK": ProductPolicy(
                product_type="POINT_PACK",
                product_name="标准额度包",
                amount=Decimal(settings.point_pack_amount),
                points=settings.point_pack_points,
            ),
            "POINT_PACK_PLUS": ProductPolicy(
                product_type="POINT_PACK_PLUS",
                product_name="进阶额度包",
                amount=Decimal(settings.point_pack_plus_amount),
                points=settings.point_pack_plus_points,
            ),
        }
        if normalized not in defaults:
            raise AppException(code=1001, message="不支持的额度套餐")

        policy = defaults[normalized]
        return ProductPolicy(
            product_type=policy.product_type,
            product_name=policy.product_name,
            amount=self._read_decimal(f"{policy.product_type}_AMOUNT", policy.amount),
            points=self._read_int(f"{policy.product_type}_POINTS", policy.points),
            first_purchase_only=policy.first_purchase_only,
        )

    def _read_int(self, key: str, default: int) -> int:
        config = self.config_repo.get_by_key(key)
        if config is None or not config.config_value:
            return default
        try:
            return int(config.config_value)
        except ValueError:
            return default

    def _read_decimal(self, key: str, default: Decimal) -> Decimal:
        config = self.config_repo.get_by_key(key)
        if config is None or not config.config_value:
            return default
        try:
            return Decimal(config.config_value).quantize(Decimal("0.01"))
        except Exception:
            return default
