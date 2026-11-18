"""Server-only opcpay API. Remote exceptions/bodies never enter logs or responses."""
import httpx

from app.core.config import get_settings
from app.core.exceptions import AppException

BASE_URL = "https://ai6666.com/opcpay/api/pay/v1"


class OpcpayClient:
    def __init__(self, transport=None):
        self.transport = transport

    def request(self, path: str, body: dict | None = None) -> dict:
        key = get_settings().opcpay_api_key
        if key is None or not key.get_secret_value().strip():
            raise AppException(code=3010, message="支付服务尚未配置", status_code=503)
        try:
            with httpx.Client(timeout=30, follow_redirects=False, transport=self.transport) as client:
                response = client.request("GET" if body is None else "POST", BASE_URL + path,
                    headers={"Authorization": "Bearer " + key.get_secret_value()}, json=body)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError()
                return data
        except (httpx.HTTPError, ValueError):
            raise AppException(code=3011, message="支付结果暂待确认，请稍后使用原记录重试", status_code=503) from None

    def product(self):
        caps = self.request("/capabilities")
        product = self.request("/product")
        flags = caps.get("capabilities", {})
        if (caps.get("provider_configured") is not True or product.get("capability_status") != "ENABLED"
                or not all(flags.get(k) is True for k in ("purchase_entry", "entitlement_query", "consumption"))
                or product.get("billing_mode") != "QUANTITY" or product.get("quota_unit") != "POINT"):
            raise AppException(code=3012, message="当前支付套餐尚不可用，请联系管理员", status_code=503)
        return caps, product

    def access(self, user_id: int, amount: int = 1):
        return self.request("/access", {"user_id": str(user_id), "amount": amount})


def confirmed_consumption(data: dict, body: dict, unit: str) -> bool:
    return (data.get("status") == "SUCCEEDED" and data.get("confirmed") is True
            and data.get("idempotency_key") == body["idempotency_key"]
            and type(data.get("consumed")) is int and data["consumed"] == body["amount"]
            and data.get("quota_unit") == unit)
