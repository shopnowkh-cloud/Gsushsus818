import os
import asyncio
import logging
import tempfile
import base64
import secrets
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Security, status as http_status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from bakong_khqr import KHQR

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BAKONG_TOKEN = os.environ.get("BAKONG_TOKEN", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_PORT = int(os.environ.get("API_PORT", 8000))

KHQR_API_KEYS_RAW = os.environ.get("KHQR_API_KEYS", "")
API_KEYS = set(k.strip() for k in KHQR_API_KEYS_RAW.split(",") if k.strip())
if not API_KEYS:
    auto_key = secrets.token_hex(24)
    API_KEYS.add(auto_key)
    logger.warning(f"No KHQR_API_KEYS set. Auto-generated API key: {auto_key}")

khqr = KHQR(BAKONG_TOKEN)

(
    ASK_ACCOUNT,
    ASK_NAME,
    ASK_CITY,
    ASK_AMOUNT,
    ASK_CURRENCY,
    ASK_BILL,
    CONFIRM_PAY,
) = range(7)

CHECK_MD5 = 10


# ─────────────────────────────────────────────
#  REST API (FastAPI)
# ─────────────────────────────────────────────

api = FastAPI(
    title="Bakong KHQR Payment API",
    description=(
        "REST API សម្រាប់ Bakong KHQR Payment Integration\n\n"
        "## Authentication\n"
        "Pass your API key via `X-API-Key` header.\n\n"
        "## Endpoints\n"
        "- `POST /api/generate-qr` — បង្កើត QR Code\n"
        "- `POST /api/check-payment` — ពិនិត្យការទូទាត់\n"
        "- `GET /api/payment/{md5}` — ទទួលព័ត៌មានការទូទាត់\n"
        "- `POST /api/bulk-check` — ពិនិត្យច្រើន MD5 (max 50)\n"
    ),
    version="1.0.0",
)

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_key(key: str = Security(api_key_header)):
    if not key or key not in API_KEYS:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Use X-API-Key header.",
        )
    return key


class GenerateQRRequest(BaseModel):
    bank_account: str = Field(..., description="Bakong account e.g. name@aclb")
    merchant_name: str = Field(..., description="Merchant name")
    merchant_city: str = Field(..., description="City e.g. Phnom Penh")
    amount: float = Field(..., description="Payment amount")
    currency: str = Field(..., description="USD or KHR")
    bill_number: Optional[str] = Field(None, description="Invoice number (optional)")
    store_label: Optional[str] = Field(None, description="Store label (optional)")
    phone_number: Optional[str] = Field(None, description="Phone number (optional)")
    terminal_label: Optional[str] = Field(None, description="Terminal label (optional)")
    static: bool = Field(False, description="Static QR (reusable) or dynamic (one-time)")
    expiration: int = Field(1, description="Expiry in days")
    include_image: bool = Field(True, description="Return base64 PNG image")
    include_deeplink: bool = Field(True, description="Return Bakong deep link")
    app_name: Optional[str] = Field("MyApp", description="App name for deep link")


class CheckPaymentRequest(BaseModel):
    md5: str = Field(..., description="MD5 hash from generate-qr (32 chars)")


class BulkCheckRequest(BaseModel):
    md5_list: list[str] = Field(..., description="List of MD5 hashes (max 50)")


@api.get("/", tags=["Info"])
async def root():
    return {
        "name": "Bakong KHQR Payment API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "generate_qr":    "POST /api/generate-qr",
            "check_payment":  "POST /api/check-payment",
            "get_payment":    "GET  /api/payment/{md5}",
            "bulk_check":     "POST /api/bulk-check",
        },
    }


@api.get("/health", tags=["Info"])
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@api.post("/api/generate-qr", tags=["Payment"])
async def generate_qr(body: GenerateQRRequest, _: str = Security(verify_key)):
    if body.currency not in ("USD", "KHR"):
        raise HTTPException(400, "currency must be USD or KHR")
    if body.amount <= 0:
        raise HTTPException(400, "amount must be greater than 0")

    try:
        qr_string = khqr.create_qr(
            bank_account=body.bank_account,
            merchant_name=body.merchant_name,
            merchant_city=body.merchant_city,
            amount=body.amount,
            currency=body.currency,
            bill_number=body.bill_number,
            store_label=body.store_label,
            phone_number=body.phone_number,
            terminal_label=body.terminal_label,
            static=body.static,
            expiration=body.expiration,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to generate QR: {e}")

    md5 = khqr.generate_md5(qr_string)

    image_base64 = None
    if body.include_image:
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            khqr.qr_image(qr_string, format="png", output_path=tmp_path)
            with open(tmp_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode()
            os.unlink(tmp_path)
        except Exception as e:
            logger.warning(f"Image generation failed: {e}")

    deeplink = None
    if body.include_deeplink:
        try:
            deeplink = khqr.generate_deeplink(qr=qr_string, appName=body.app_name or "MyApp")
        except Exception as e:
            logger.warning(f"Deeplink generation failed: {e}")

    return {
        "success": True,
        "qr_string": qr_string,
        "md5": md5,
        "image_base64": image_base64,
        "deeplink": deeplink,
        "currency": body.currency,
        "amount": body.amount,
        "merchant_name": body.merchant_name,
        "bank_account": body.bank_account,
        "expires_in_days": body.expiration,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


@api.post("/api/check-payment", tags=["Payment"])
async def check_payment(body: CheckPaymentRequest, _: str = Security(verify_key)):
    if len(body.md5) != 32:
        raise HTTPException(400, "md5 must be 32 characters")
    try:
        payment_status = khqr.check_payment(body.md5)
        is_paid = payment_status == "PAID"
        transaction = khqr.get_payment(body.md5) if is_paid else None
        return {"success": True, "md5": body.md5, "status": payment_status,
                "is_paid": is_paid, "transaction": transaction}
    except Exception as e:
        raise HTTPException(500, f"Failed to check payment: {e}")


@api.get("/api/payment/{md5}", tags=["Payment"])
async def get_payment(md5: str, _: str = Security(verify_key)):
    if len(md5) != 32:
        raise HTTPException(400, "md5 must be 32 characters")
    try:
        payment_status = khqr.check_payment(md5)
        is_paid = payment_status == "PAID"
        transaction = khqr.get_payment(md5) if is_paid else None
        return {"success": True, "md5": md5, "status": payment_status,
                "is_paid": is_paid, "transaction": transaction}
    except Exception as e:
        raise HTTPException(500, f"Failed to get payment: {e}")


@api.post("/api/bulk-check", tags=["Payment"])
async def bulk_check(body: BulkCheckRequest, _: str = Security(verify_key)):
    if not body.md5_list:
        raise HTTPException(400, "md5_list cannot be empty")
    if len(body.md5_list) > 50:
        raise HTTPException(400, "md5_list cannot exceed 50 items")
    try:
        paid = khqr.check_bulk_payments(body.md5_list)
        return {"success": True, "total": len(body.md5_list),
                "paid_count": len(paid), "paid_md5s": paid}
    except Exception as e:
        raise HTTPException(500, f"Failed to bulk check: {e}")


# ─────────────────────────────────────────────
#  TELEGRAM BOT
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("💳 បង្កើតការទូទាត់", callback_data="create_payment")],
        [InlineKeyboardButton("🔍 ពិនិត្យការទូទាត់", callback_data="check_payment")],
        [InlineKeyboardButton("ℹ️ អំពី Bakong KHQR", callback_data="about")],
    ]
    await update.message.reply_text(
        "👋 សូមស្វាគមន៍មកកាន់ Bot Bakong KHQR Payment!\n\n"
        "🏦 Bot នេះអាចជួយអ្នក:\n"
        "• 💳 បង្កើត QR Code សម្រាប់ទទួលប្រាក់\n"
        "• 🔍 ពិនិត្យស្ថានភាពការទូទាត់\n\n"
        "ជ្រើសរើសប្រតិបត្តិការ:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "create_payment":
        await query.edit_message_text(
            "💳 *បង្កើត QR Code ទូទាត់ Bakong*\n\n"
            "📝 សូមបញ្ចូល Bakong Account របស់អ្នក\n"
            "_(ឧ: yourname@aclb, yourname@wing)_",
            parse_mode="Markdown",
        )
        return ASK_ACCOUNT
    elif query.data == "check_payment":
        await query.edit_message_text(
            "🔍 *ពិនិត្យស្ថានភាពការទូទាត់*\n\n"
            "📝 សូមបញ្ចូល MD5 Hash នៃ QR Code:\n_(32 តួអក្សរ)_",
            parse_mode="Markdown",
        )
        return CHECK_MD5
    elif query.data == "about":
        await query.edit_message_text(
            "ℹ️ *អំពី Bakong KHQR Payment*\n\n"
            "🏦 Bakong គឺជាប្រព័ន្ធទូទាត់ឌីជីថលជាតិ\n"
            "ដែលបង្កើតឡើងដោយ *ធនាគារជាតិនៃកម្ពុជា*\n\n"
            "✅ គាំទ្ររូបិយប័ណ្ណ: *USD* និង *KHR*\n"
            "✅ ទូទាត់ភ្លាមៗ ២៤/៧\n"
            "✅ សុវត្ថិភាព និងត្រឹមត្រូវ\n\n"
            "🔗 ចុច /start ដើម្បីចាប់ផ្តើម",
            parse_mode="Markdown",
        )
        return ConversationHandler.END


async def ask_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["bank_account"] = update.message.text.strip()
    await update.message.reply_text(
        "👤 *ឈ្មោះអ្នកទទួល*\n\n📝 សូមបញ្ចូលឈ្មោះ Merchant:\n_(ឧ: Dara Shop)_",
        parse_mode="Markdown",
    )
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["merchant_name"] = update.message.text.strip()
    await update.message.reply_text(
        "🏙️ *ទីក្រុង*\n\n📝 សូមបញ្ចូលឈ្មោះទីក្រុង:\n_(ឧ: Phnom Penh)_",
        parse_mode="Markdown",
    )
    return ASK_CITY


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["merchant_city"] = update.message.text.strip()
    await update.message.reply_text(
        "💰 *ចំនួនទឹកប្រាក់*\n\n📝 សូមបញ្ចូលចំនួន:\n_(ឧ: 5.00, 25000)_",
        parse_mode="Markdown",
    )
    return ASK_AMOUNT


async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError()
        context.user_data["amount"] = amount
    except ValueError:
        await update.message.reply_text("❌ ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ។ សូមបញ្ចូលជាលេខ")
        return ASK_AMOUNT

    keyboard = [[
        InlineKeyboardButton("🇺🇸 USD", callback_data="currency_USD"),
        InlineKeyboardButton("🇰🇭 KHR", callback_data="currency_KHR"),
    ]]
    await update.message.reply_text(
        "💱 *រូបិយប័ណ្ណ*\n\nសូមជ្រើសរើស:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )
    return ASK_CURRENCY


async def ask_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["currency"] = query.data.replace("currency_", "")
    await query.edit_message_text(
        "🧾 *លេខវិក្កយបត្រ (ស្រេចចិត្ត)*\n\n"
        "📝 បញ្ចូលលេខ ឬចុច /skip:\n_(ឧ: INV001)_",
        parse_mode="Markdown",
    )
    return ASK_BILL


async def ask_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["bill_number"] = None if text.lower() == "/skip" else text
    return await generate_qr_bot(update, context)


async def skip_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["bill_number"] = None
    return await generate_qr_bot(update, context)


async def generate_qr_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    sym = "$" if data["currency"] == "USD" else "៛"
    amt = f"{data['amount']:,.2f}" if data["currency"] == "USD" else f"{int(data['amount']):,}"
    msg = await update.message.reply_text("⏳ កំពុងបង្កើត QR Code...")

    try:
        qr_string = khqr.create_qr(
            bank_account=data["bank_account"],
            merchant_name=data["merchant_name"],
            merchant_city=data["merchant_city"],
            amount=data["amount"],
            currency=data["currency"],
            bill_number=data.get("bill_number"),
        )
        md5_hash = khqr.generate_md5(qr_string)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name
        khqr.qr_image(qr_string, format="png", output_path=tmp_path)
        deeplink = khqr.generate_deeplink(qr=qr_string, appName="Bakong Bot")

        keyboard = [
            [InlineKeyboardButton("🔍 ពិនិត្យការទូទាត់", callback_data=f"check_{md5_hash}")],
            [InlineKeyboardButton("🔄 បង្កើតថ្មី", callback_data="create_payment")],
        ]
        caption = (
            f"✅ *QR Code ទូទាត់ Bakong*\n\n"
            f"👤 អ្នកទទួល: `{data['merchant_name']}`\n"
            f"🏙️ ទីក្រុង: `{data['merchant_city']}`\n"
            f"💰 ចំនួន: `{sym}{amt}`\n"
            f"🏦 Account: `{data['bank_account']}`\n"
        )
        if data.get("bill_number"):
            caption += f"🧾 វិក្កយបត្រ: `{data['bill_number']}`\n"
        caption += f"\n🔑 MD5: `{md5_hash}`\n\n📱 _ស្កែន QR Code ជាមួយ Bakong App_"

        await msg.delete()
        await update.message.reply_photo(
            photo=open(tmp_path, "rb"),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        if deeplink:
            await update.message.reply_text(f"🔗 *Deep Link:*\n{deeplink}", parse_mode="Markdown")
        os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"QR error: {e}")
        await msg.edit_text(
            f"❌ បរាជ័យក្នុងការបង្កើត QR Code\n\nកំហុស: {e}\n\n"
            "ចុច /pay ដើម្បីព្យាយាមម្តងទៀត"
        )

    context.user_data.clear()
    return ConversationHandler.END


async def check_payment_md5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    md5 = update.message.text.strip()
    if len(md5) != 32:
        await update.message.reply_text("❌ MD5 ត្រូវតែមាន 32 តួអក្សរ។ ព្យាយាមម្តងទៀត")
        return CHECK_MD5

    await update.message.reply_text("⏳ កំពុងពិនិត្យ...")
    try:
        s = khqr.check_payment(md5)
        if s == "PAID":
            info = khqr.get_payment(md5)
            text = "✅ *ការទូទាត់បានជោគជ័យ!*\n\n"
            if info:
                for k, v in info.items():
                    if v:
                        text += f"• {k}: `{v}`\n"
        else:
            text = "⏳ *មិនទាន់ទូទាត់*\n\nQR Code នៅតែសុពលភាព។"

        keyboard = [
            [InlineKeyboardButton("🔄 ពិនិត្យម្តងទៀត", callback_data=f"check_{md5}")],
            [InlineKeyboardButton("🏠 ត្រឡប់ទៅដើម", callback_data="home")],
        ]
        await update.message.reply_text(text, parse_mode="Markdown",
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await update.message.reply_text(f"❌ កំហុស: {e}")

    return ConversationHandler.END


async def inline_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("check_"):
        md5 = query.data.replace("check_", "")
        await query.edit_message_text("⏳ កំពុងពិនិត្យ...")
        try:
            s = khqr.check_payment(md5)
            if s == "PAID":
                info = khqr.get_payment(md5)
                text = "✅ *ការទូទាត់បានជោគជ័យ!*\n\n"
                if info:
                    for k, v in info.items():
                        if v:
                            text += f"• {k}: `{v}`\n"
            else:
                text = f"⏳ *មិនទាន់ទូទាត់*\n\nMD5: `{md5}`\n\nQR Code នៅតែសុពលភាព។"

            keyboard = [
                [InlineKeyboardButton("🔄 ពិនិត្យម្តងទៀត", callback_data=f"check_{md5}")],
                [InlineKeyboardButton("💳 ការទូទាត់ថ្មី", callback_data="create_payment")],
            ]
            await query.edit_message_text(text, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await query.edit_message_text(f"❌ កំហុស: {e}")

    elif query.data == "home":
        keyboard = [
            [InlineKeyboardButton("💳 បង្កើតការទូទាត់", callback_data="create_payment")],
            [InlineKeyboardButton("🔍 ពិនិត្យការទូទាត់", callback_data="check_payment")],
            [InlineKeyboardButton("ℹ️ អំពី Bakong KHQR", callback_data="about")],
        ]
        await query.edit_message_text(
            "👋 សូមស្វាគមន៍!\n\nជ្រើសរើសប្រតិបត្តិការ:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "💳 *បង្កើត QR Code ទូទាត់ Bakong*\n\n"
        "📝 សូមបញ្ចូល Bakong Account:\n_(ឧ: yourname@aclb)_",
        parse_mode="Markdown",
    )
    return ASK_ACCOUNT


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔍 *ពិនិត្យការទូទាត់*\n\n📝 សូមបញ្ចូល MD5 Hash:\n_(32 តួអក្សរ)_",
        parse_mode="Markdown",
    )
    return CHECK_MD5


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ បោះបង់ប្រតិបត្តិការ។\n\nចុច /start ដើម្បីចាប់ផ្តើមថ្មី។")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *ជំនួយ - Bakong KHQR Bot*\n\n"
        "🔹 /start - ចាប់ផ្តើម\n"
        "🔹 /pay - បង្កើត QR Code\n"
        "🔹 /check - ពិនិត្យការទូទាត់\n"
        "🔹 /cancel - បោះបង់\n"
        "🔹 /help - ជំនួយ\n\n"
        "🏦 _Powered by Bakong NBC Cambodia_",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
#  RUN BOTH BOT + API TOGETHER
# ─────────────────────────────────────────────

async def run_api():
    config = uvicorn.Config(api, host="0.0.0.0", port=API_PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    payment_conv = ConversationHandler(
        entry_points=[
            CommandHandler("pay", pay_command),
            CallbackQueryHandler(button_handler, pattern="^create_payment$"),
        ],
        states={
            ASK_ACCOUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_account)],
            ASK_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_CITY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],
            ASK_AMOUNT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_CURRENCY: [CallbackQueryHandler(ask_currency, pattern="^currency_")],
            ASK_BILL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_bill),
                CommandHandler("skip", skip_bill),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    check_conv = ConversationHandler(
        entry_points=[
            CommandHandler("check", check_command),
            CallbackQueryHandler(button_handler, pattern="^check_payment$"),
        ],
        states={
            CHECK_MD5: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_payment_md5)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(payment_conv)
    application.add_handler(check_conv)
    application.add_handler(CallbackQueryHandler(inline_check_payment))

    async with application:
        await application.initialize()
        await application.start()
        logger.info("Telegram Bot is running...")
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        await asyncio.Event().wait()
        await application.updater.stop()
        await application.stop()


async def main():
    logger.info(f"Starting Bakong KHQR Bot + API on port {API_PORT}...")
    await asyncio.gather(run_bot(), run_api())


if __name__ == "__main__":
    asyncio.run(main())
