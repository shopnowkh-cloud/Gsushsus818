import os
import base64
import tempfile
import hashlib
import secrets
import logging
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Security, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from bakong_khqr import KHQR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BAKONG_TOKEN = os.environ.get("BAKONG_TOKEN", "")
API_KEYS_RAW = os.environ.get("KHQR_API_KEYS", "")
API_KEYS = set(k.strip() for k in API_KEYS_RAW.split(",") if k.strip()) if API_KEYS_RAW else set()

if not API_KEYS:
    default_key = os.environ.get("KHQR_DEFAULT_API_KEY", "")
    if not default_key:
        default_key = secrets.token_urlsafe(32)
        logger.warning(f"No API keys configured. Auto-generated key: {default_key}")
        logger.warning("Set KHQR_API_KEYS environment variable to configure your own keys.")
    API_KEYS.add(default_key)
    logger.info(f"Active API key: {list(API_KEYS)[0]}")

khqr = KHQR(BAKONG_TOKEN)

app = FastAPI(
    title="Bakong KHQR Payment API",
    description=(
        "REST API for Bakong KHQR payment integration.\n\n"
        "## Authentication\n"
        "All endpoints require an API key passed via the `X-API-Key` header.\n\n"
        "## Features\n"
        "- Generate KHQR QR codes (PNG image + MD5 + deeplink)\n"
        "- Check single or bulk payment status\n"
        "- Retrieve paid transaction details\n"
        "- Generate Bakong deep links\n"
    ),
    version="1.0.0",
    contact={"name": "Bakong KHQR API"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Pass your key in the X-API-Key header.",
        )
    return api_key


class GenerateQRRequest(BaseModel):
    model_config = {"json_schema_extra": {"example": {
        "bank_account": "yourname@aclb",
        "merchant_name": "Dara Shop",
        "merchant_city": "Phnom Penh",
        "amount": 5.00,
        "currency": "USD",
        "bill_number": "INV-001",
        "include_image": True,
        "include_deeplink": True,
    }}}

    bank_account: str = Field(..., description="Bakong account (e.g. name@bank)")
    merchant_name: str = Field(..., description="Merchant or recipient name")
    merchant_city: str = Field(..., description="Merchant city")
    amount: float = Field(..., description="Payment amount")
    currency: str = Field(..., description="Currency: USD or KHR")
    store_label: Optional[str] = Field(None, description="Store label (optional)")
    phone_number: Optional[str] = Field(None, description="Phone number (optional)")
    bill_number: Optional[str] = Field(None, description="Bill/invoice number (optional)")
    terminal_label: Optional[str] = Field(None, description="Terminal label (optional)")
    static: bool = Field(False, description="True = static QR (reusable), False = dynamic (one-time)")
    expiration: int = Field(1, description="QR expiration in days (default: 1)")
    include_image: bool = Field(True, description="Include base64 PNG image in response")
    include_deeplink: bool = Field(True, description="Include Bakong deep link in response")
    app_name: Optional[str] = Field("MyApp", description="Your app name for the deep link")
    callback_url: Optional[str] = Field("https://bakong.nbc.org.kh", description="Callback URL for deep link")


class GenerateQRResponse(BaseModel):
    success: bool
    qr_string: str
    md5: str
    image_base64: Optional[str] = None
    deeplink: Optional[str] = None
    currency: str
    amount: float
    merchant_name: str
    bank_account: str
    expires_in_days: int
    generated_at: str


class CheckPaymentRequest(BaseModel):
    md5: str = Field(..., description="MD5 hash from generate-qr response (32 chars)")


class CheckPaymentResponse(BaseModel):
    success: bool
    md5: str
    status: str
    is_paid: bool
    transaction: Optional[dict] = None


class BulkCheckRequest(BaseModel):
    md5_list: list[str] = Field(..., description="List of MD5 hashes (max 50)")


class BulkCheckResponse(BaseModel):
    success: bool
    total: int
    paid_count: int
    paid_md5s: list[str]


class DeeplinkRequest(BaseModel):
    qr_string: str = Field(..., description="QR string from generate-qr response")
    app_name: Optional[str] = Field("MyApp", description="Your app name")
    callback_url: Optional[str] = Field("https://bakong.nbc.org.kh", description="Callback URL")
    app_icon_url: Optional[str] = Field(
        "https://bakong.nbc.gov.kh/images/logo.svg", description="Your app icon URL"
    )


@app.get("/", tags=["Info"])
async def root():
    return {
        "name": "Bakong KHQR Payment API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "generate_qr": "POST /api/v1/generate-qr",
            "check_payment": "POST /api/v1/check-payment",
            "get_payment": "GET /api/v1/payment/{md5}",
            "bulk_check": "POST /api/v1/bulk-check",
            "generate_deeplink": "POST /api/v1/deeplink",
        },
    }


@app.post(
    "/api/v1/generate-qr",
    response_model=GenerateQRResponse,
    tags=["QR Code"],
    summary="Generate KHQR QR Code",
    description=(
        "Generate a Bakong KHQR payment QR code.\n\n"
        "Returns the QR string, MD5 hash for payment checking, "
        "optional base64 PNG image, and optional Bakong deep link."
    ),
)
async def generate_qr(
    body: GenerateQRRequest,
    _: str = Depends(verify_api_key),
):
    if body.currency not in ("USD", "KHR"):
        raise HTTPException(status_code=400, detail="currency must be 'USD' or 'KHR'")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    if body.expiration < 1:
        raise HTTPException(status_code=400, detail="expiration must be at least 1 day")

    try:
        qr_string = khqr.create_qr(
            bank_account=body.bank_account,
            merchant_name=body.merchant_name,
            merchant_city=body.merchant_city,
            amount=body.amount,
            currency=body.currency,
            store_label=body.store_label,
            phone_number=body.phone_number,
            bill_number=body.bill_number,
            terminal_label=body.terminal_label,
            static=body.static,
            expiration=body.expiration,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate QR: {str(e)}")

    md5 = khqr.generate_md5(qr_string)

    image_base64 = None
    if body.include_image:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            khqr.qr_image(qr_string, format="png", output_path=tmp_path)
            with open(tmp_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            os.unlink(tmp_path)
        except Exception as e:
            logger.warning(f"Failed to generate QR image: {e}")

    deeplink = None
    if body.include_deeplink:
        try:
            deeplink = khqr.generate_deeplink(
                qr=qr_string,
                callback=body.callback_url or "https://bakong.nbc.org.kh",
                appName=body.app_name or "MyApp",
                appIconUrl="https://bakong.nbc.gov.kh/images/logo.svg",
            )
        except Exception as e:
            logger.warning(f"Failed to generate deeplink: {e}")

    return GenerateQRResponse(
        success=True,
        qr_string=qr_string,
        md5=md5,
        image_base64=image_base64,
        deeplink=deeplink,
        currency=body.currency,
        amount=body.amount,
        merchant_name=body.merchant_name,
        bank_account=body.bank_account,
        expires_in_days=body.expiration,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


@app.post(
    "/api/v1/check-payment",
    response_model=CheckPaymentResponse,
    tags=["Payment"],
    summary="Check Payment Status",
    description="Check if a KHQR payment has been completed using the MD5 hash.",
)
async def check_payment(
    body: CheckPaymentRequest,
    _: str = Depends(verify_api_key),
):
    if len(body.md5) != 32:
        raise HTTPException(status_code=400, detail="md5 must be 32 characters")

    try:
        payment_status = khqr.check_payment(body.md5)
        is_paid = payment_status == "PAID"

        transaction = None
        if is_paid:
            try:
                transaction = khqr.get_payment(body.md5)
            except Exception:
                pass

        return CheckPaymentResponse(
            success=True,
            md5=body.md5,
            status=payment_status,
            is_paid=is_paid,
            transaction=transaction,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check payment: {str(e)}")


@app.get(
    "/api/v1/payment/{md5}",
    tags=["Payment"],
    summary="Get Payment Details",
    description="Retrieve full transaction details for a paid KHQR payment.",
)
async def get_payment(
    md5: str,
    _: str = Depends(verify_api_key),
):
    if len(md5) != 32:
        raise HTTPException(status_code=400, detail="md5 must be 32 characters")

    try:
        payment_status = khqr.check_payment(md5)
        if payment_status != "PAID":
            return JSONResponse(
                status_code=202,
                content={
                    "success": True,
                    "md5": md5,
                    "status": "UNPAID",
                    "is_paid": False,
                    "transaction": None,
                    "message": "Payment has not been completed yet.",
                },
            )

        transaction = khqr.get_payment(md5)
        return {
            "success": True,
            "md5": md5,
            "status": "PAID",
            "is_paid": True,
            "transaction": transaction,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get payment: {str(e)}")


@app.post(
    "/api/v1/bulk-check",
    response_model=BulkCheckResponse,
    tags=["Payment"],
    summary="Bulk Payment Status Check",
    description="Check payment status for multiple MD5 hashes at once (max 50).",
)
async def bulk_check(
    body: BulkCheckRequest,
    _: str = Depends(verify_api_key),
):
    if not body.md5_list:
        raise HTTPException(status_code=400, detail="md5_list cannot be empty")
    if len(body.md5_list) > 50:
        raise HTTPException(status_code=400, detail="md5_list cannot exceed 50 items")
    for md5 in body.md5_list:
        if len(md5) != 32:
            raise HTTPException(status_code=400, detail=f"Invalid MD5: {md5} (must be 32 characters)")

    try:
        paid_md5s = khqr.check_bulk_payments(body.md5_list)
        return BulkCheckResponse(
            success=True,
            total=len(body.md5_list),
            paid_count=len(paid_md5s),
            paid_md5s=paid_md5s,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bulk check: {str(e)}")


@app.post(
    "/api/v1/deeplink",
    tags=["QR Code"],
    summary="Generate Bakong Deep Link",
    description="Generate a Bakong app deep link from an existing QR string.",
)
async def generate_deeplink(
    body: DeeplinkRequest,
    _: str = Depends(verify_api_key),
):
    try:
        deeplink = khqr.generate_deeplink(
            qr=body.qr_string,
            callback=body.callback_url or "https://bakong.nbc.org.kh",
            appName=body.app_name or "MyApp",
            appIconUrl=body.app_icon_url or "https://bakong.nbc.gov.kh/images/logo.svg",
        )
        return {"success": True, "deeplink": deeplink}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate deeplink: {str(e)}")


@app.get("/health", tags=["Info"])
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 9000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
