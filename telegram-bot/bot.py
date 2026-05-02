import os
import logging
import tempfile
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("💳 បង្កើតការទូទាត់", callback_data="create_payment")],
        [InlineKeyboardButton("🔍 ពិនិត្យការទូទាត់", callback_data="check_payment")],
        [InlineKeyboardButton("ℹ️ អំពី Bakong KHQR", callback_data="about")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 សូមស្វាគមន៍មកកាន់ Bot Bakong KHQR Payment!\n\n"
        "🏦 Bot នេះអាចជួយអ្នក:\n"
        "• 💳 បង្កើត QR Code សម្រាប់ទទួលប្រាក់\n"
        "• 🔍 ពិនិត្យស្ថានភាពការទូទាត់\n\n"
        "ជ្រើសរើសប្រតិបត្តិការ:",
        reply_markup=reply_markup,
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
            "📝 សូមបញ្ចូល MD5 Hash នៃ QR Code:\n"
            "_(32 តួអក្សរ)_",
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
        "👤 *ឈ្មោះអ្នកទទួល*\n\n"
        "📝 សូមបញ្ចូលឈ្មោះ Merchant/អ្នកទទួល:\n"
        "_(ឧ: Dara Shop, Sokha Store)_",
        parse_mode="Markdown",
    )
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["merchant_name"] = update.message.text.strip()
    await update.message.reply_text(
        "🏙️ *ទីក្រុង*\n\n"
        "📝 សូមបញ្ចូលឈ្មោះទីក្រុង:\n"
        "_(ឧ: Phnom Penh, Siem Reap)_",
        parse_mode="Markdown",
    )
    return ASK_CITY


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["merchant_city"] = update.message.text.strip()
    await update.message.reply_text(
        "💰 *ចំនួនទឹកប្រាក់*\n\n"
        "📝 សូមបញ្ចូលចំនួនទឹកប្រាក់:\n"
        "_(ឧ: 5.00, 100, 25000)_",
        parse_mode="Markdown",
    )
    return ASK_AMOUNT


async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError("Amount must be positive")
        context.user_data["amount"] = amount
    except ValueError:
        await update.message.reply_text(
            "❌ ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ។ សូមបញ្ចូលជាលេខ (ឧ: 5.00)"
        )
        return ASK_AMOUNT

    keyboard = [
        [
            InlineKeyboardButton("🇺🇸 USD", callback_data="currency_USD"),
            InlineKeyboardButton("🇰🇭 KHR", callback_data="currency_KHR"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💱 *រូបិយប័ណ្ណ*\n\nសូមជ្រើសរើសរូបិយប័ណ្ណ:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return ASK_CURRENCY


async def ask_currency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    currency = query.data.replace("currency_", "")
    context.user_data["currency"] = currency

    await query.edit_message_text(
        "🧾 *លេខវិក្កយបត្រ (ស្រេចចិត្ត)*\n\n"
        "📝 សូមបញ្ចូលលេខវិក្កយបត្រ ឬចុច /skip ដើម្បីរំលង:\n"
        "_(ឧ: INV001, ORDER-2024)_",
        parse_mode="Markdown",
    )
    return ASK_BILL


async def ask_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text.lower() != "/skip":
        context.user_data["bill_number"] = text
    else:
        context.user_data["bill_number"] = None
    return await generate_qr(update, context)


async def skip_bill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["bill_number"] = None
    return await generate_qr(update, context)


async def generate_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    currency_symbol = "$" if data["currency"] == "USD" else "៛"
    amount_display = f"{data['amount']:,.2f}" if data["currency"] == "USD" else f"{int(data['amount']):,}"

    processing_msg = await update.message.reply_text("⏳ កំពុងបង្កើត QR Code...")

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

        deeplink = khqr.generate_deeplink(
            qr=qr_string,
            appName="Bakong Bot",
        )

        keyboard = [
            [InlineKeyboardButton("🔍 ពិនិត្យការទូទាត់", callback_data=f"check_{md5_hash}")],
            [InlineKeyboardButton("🔄 បង្កើតថ្មី", callback_data="create_payment")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        caption = (
            f"✅ *QR Code ទូទាត់ Bakong*\n\n"
            f"👤 អ្នកទទួល: `{data['merchant_name']}`\n"
            f"🏙️ ទីក្រុង: `{data['merchant_city']}`\n"
            f"💰 ចំនួន: `{currency_symbol}{amount_display}`\n"
            f"🏦 Account: `{data['bank_account']}`\n"
        )
        if data.get("bill_number"):
            caption += f"🧾 វិក្កយបត្រ: `{data['bill_number']}`\n"
        caption += f"\n🔑 MD5: `{md5_hash}`\n\n"
        caption += "📱 _ស្កែន QR Code ជាមួយ Bakong App_"

        await processing_msg.delete()
        await update.message.reply_photo(
            photo=open(tmp_path, "rb"),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

        if deeplink:
            await update.message.reply_text(
                f"🔗 *Deep Link Bakong:*\n{deeplink}",
                parse_mode="Markdown",
            )

        os.unlink(tmp_path)

    except Exception as e:
        logger.error(f"Error generating QR: {e}")
        await processing_msg.edit_text(
            f"❌ បរាជ័យក្នុងការបង្កើត QR Code\n\nកំហុស: {str(e)}\n\n"
            "សូមពិនិត្យ Bakong Account របស់អ្នក ហើយព្យាយាមម្តងទៀត\n"
            "ចុច /pay ដើម្បីចាប់ផ្តើមម្តងទៀត"
        )

    context.user_data.clear()
    return ConversationHandler.END


async def check_payment_md5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    md5 = update.message.text.strip()
    if len(md5) != 32:
        await update.message.reply_text(
            "❌ MD5 Hash មិនត្រឹមត្រូវ។\n"
            "MD5 ត្រូវតែមាន 32 តួអក្សរ។\n\n"
            "ព្យាយាមម្តងទៀត ឬចុច /cancel ដើម្បីបោះបង់"
        )
        return CHECK_MD5

    await update.message.reply_text("⏳ កំពុងពិនិត្យការទូទាត់...")

    try:
        status = khqr.check_payment(md5)

        if status == "PAID":
            payment_info = khqr.get_payment(md5)
            text = "✅ *ការទូទាត់បានជោគជ័យ!*\n\n"
            if payment_info:
                for key, value in payment_info.items():
                    if value:
                        text += f"• {key}: `{value}`\n"
        else:
            text = (
                "⏳ *ការទូទាត់មិនទាន់បានអនុវត្ត*\n\n"
                "QR Code នៅតែសុពលភាព។\n"
                "សូមរង់ចាំការទូទាត់ពីអតិថិជន។"
            )

        keyboard = [
            [InlineKeyboardButton("🔄 ពិនិត្យម្តងទៀត", callback_data=f"check_{md5}")],
            [InlineKeyboardButton("🏠 ត្រឡប់ទៅដើម", callback_data="home")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error checking payment: {e}")
        await update.message.reply_text(
            f"❌ បរាជ័យក្នុងការពិនិត្យការទូទាត់\n\nកំហុស: {str(e)}"
        )

    return ConversationHandler.END


async def inline_check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data.startswith("check_"):
        md5 = query.data.replace("check_", "")
        await query.edit_message_text("⏳ កំពុងពិនិត្យការទូទាត់...")

        try:
            status = khqr.check_payment(md5)

            if status == "PAID":
                payment_info = khqr.get_payment(md5)
                text = "✅ *ការទូទាត់បានជោគជ័យ!*\n\n"
                if payment_info:
                    for key, value in payment_info.items():
                        if value:
                            text += f"• {key}: `{value}`\n"
            else:
                text = (
                    "⏳ *ការទូទាត់មិនទាន់បានអនុវត្ត*\n\n"
                    f"MD5: `{md5}`\n\n"
                    "QR Code នៅតែសុពលភាព។\n"
                    "សូមរង់ចាំការទូទាត់ពីអតិថិជន។"
                )

            keyboard = [
                [InlineKeyboardButton("🔄 ពិនិត្យម្តងទៀត", callback_data=f"check_{md5}")],
                [InlineKeyboardButton("💳 ការទូទាត់ថ្មី", callback_data="create_payment")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            await query.edit_message_text(f"❌ បរាជ័យក្នុងការពិនិត្យ\n\nកំហុស: {str(e)}")

    elif query.data == "home":
        keyboard = [
            [InlineKeyboardButton("💳 បង្កើតការទូទាត់", callback_data="create_payment")],
            [InlineKeyboardButton("🔍 ពិនិត្យការទូទាត់", callback_data="check_payment")],
            [InlineKeyboardButton("ℹ️ អំពី Bakong KHQR", callback_data="about")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👋 សូមស្វាគមន៍មកកាន់ Bot Bakong KHQR Payment!\n\n"
            "ជ្រើសរើសប្រតិបត្តិការ:",
            reply_markup=reply_markup,
        )


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "💳 *បង្កើត QR Code ទូទាត់ Bakong*\n\n"
        "📝 សូមបញ្ចូល Bakong Account របស់អ្នក\n"
        "_(ឧ: yourname@aclb, yourname@wing, yourname@truemoney)_",
        parse_mode="Markdown",
    )
    return ASK_ACCOUNT


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "🔍 *ពិនិត្យស្ថានភាពការទូទាត់*\n\n"
        "📝 សូមបញ្ចូល MD5 Hash នៃ QR Code:\n"
        "_(32 តួអក្សរ)_",
        parse_mode="Markdown",
    )
    return CHECK_MD5


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "❌ បោះបង់ប្រតិបត្តិការ។\n\n"
        "ចុច /start ដើម្បីចាប់ផ្តើមម្តងទៀត។"
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *ជំនួយ - Bakong KHQR Bot*\n\n"
        "🔹 /start - ចាប់ផ្តើម\n"
        "🔹 /pay - បង្កើត QR Code ទទួលប្រាក់\n"
        "🔹 /check - ពិនិត្យស្ថានភាពការទូទាត់\n"
        "🔹 /cancel - បោះបង់ប្រតិបត្តិការ\n"
        "🔹 /help - មើលជំនួយ\n\n"
        "💡 *របៀបប្រើ:*\n"
        "1. ចុច /pay\n"
        "2. បញ្ចូល Bakong Account (ឧ: name@aclb)\n"
        "3. បញ្ចូលឈ្មោះ និងទីក្រុង\n"
        "4. បញ្ចូលចំនួន និងជ្រើសរូបិយប័ណ្ណ\n"
        "5. ទទួល QR Code ហើយចែករំលែក\n\n"
        "🏦 _Powered by Bakong NBC Cambodia_",
        parse_mode="Markdown",
    )


def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    payment_conv = ConversationHandler(
        entry_points=[
            CommandHandler("pay", pay_command),
            CallbackQueryHandler(button_handler, pattern="^create_payment$"),
        ],
        states={
            ASK_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_account)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            ASK_CURRENCY: [CallbackQueryHandler(ask_currency, pattern="^currency_")],
            ASK_BILL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_bill),
                CommandHandler("skip", skip_bill),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
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
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(payment_conv)
    application.add_handler(check_conv)
    application.add_handler(CallbackQueryHandler(inline_check_payment))

    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
