import os
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackContext
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fpdf import FPDF

# === Устанавливаем переменные вручную ===
TOKEN = "8114967909:AAH8uTGzTgZv9tSosSlCQ4nibvqlDUOCqW8"

# === Google Sheets Setup ===
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("cleaningbot-firma-3c8cec199501.json", scope)
client = gspread.authorize(creds)
sheet = client.open("CleaningBot_Orders").sheet1

# === Переменные ===
clients = {}
order_counter = 100
ADMIN_IDS = [1064450470, 1253874719]  # Твой ID и ID сотрудника
MANAGER_USERNAME = "@rimzi1221"

# === Генерация ID ===
def generate_order_id():
    global order_counter
    last_id = sheet.col_values(1)
    if len(last_id) > 1:
        try:
            last_number = int(last_id[-1].split('-')[-1])
            order_counter = last_number + 1
        except:
            pass
    return f"#DL-{order_counter:04d}"

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id in ADMIN_IDS:
        clients[chat_id] = {"step": "phone"}
        await update.message.reply_text("🔐 Режим сотрудника активирован.\n📞 Введите номер клиента:", reply_markup=ReplyKeyboardRemove())
    else:
        clients[chat_id] = {"step": "waiting_contact"}
        button = KeyboardButton("📱 Отправить номер", request_contact=True)
        markup = ReplyKeyboardMarkup(
            [[button], ["📍 Узнать локацию", "🏬 Наши филиалы"]], resize_keyboard=True
        )
        await update.message.reply_text(
            "👋 Добро пожаловать в Diamond Cleaning!\nС 2010 года мы предоставляем лучший сервис по химчистке в городе.\nПожалуйста, поделитесь своим номером, чтобы узнать статус заказа:",
            reply_markup=markup
        )

# === Обработка кнопок ===
async def handle_buttons(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "📍 Узнать локацию":
        await update.message.reply_text("📍 Главная химчистка:\nGoogle Maps: https://maps.app.goo.gl/TLCCgqqwsL4k7mfY8\nYandex Maps: https://yandex.uz/maps/-/CHwCjLmg")
    elif text == "🏬 Наши филиалы":
        await update.message.reply_text("🏬 Филиал химчистки:\nYandex Maps: https://yandex.uz/maps/-/CHwCr0OQ")

# === Обработка контакта клиента ===
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.contact.phone_number
    clean_phone = phone.replace('+', '').strip()
    values = sheet.get_all_values()
    found = False

    for row in values:
        for cell in row:
            if clean_phone in cell.replace('+', '').strip():
                found = True
                await update.message.reply_text(
                    f"🧾 Ваш заказ найден!\nID: {row[0]}\nВещи: {row[2]}\nДата сдачи: {row[3]}\nГотово: {row[6]}\nОплата: {row[5]}\nСтоимость: {row[8] if len(row) > 8 else '—'}",
                    reply_markup=ReplyKeyboardRemove()
                )
                break
    if not found:
        await update.message.reply_text("😟 Мы не нашли ваш заказ. Пожалуйста, свяжитесь с администратором.")

# === Обработка сообщений от сотрудника ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return

    text = update.message.text.replace(" ", "")
    if chat_id not in clients:
        await update.message.reply_text("Напишите /start, чтобы начать ввод данных клиента.")
        return

    data = clients[chat_id]

    if data["step"] == "phone":
        data["phone"] = text
        data["step"] = "items"
        await update.message.reply_text("👕 Укажите список вещей, которые сдал клиент:")

    elif data["step"] == "items":
        data["items"] = update.message.text
        data["step"] = "price"
        await update.message.reply_text("💵 Укажите стоимость за единицу (в сумах):")

    elif data["step"] == "price":
        data["price"] = text
        data["step"] = "quantity"
        await update.message.reply_text("🔢 Укажите количество вещей:")

    elif data["step"] == "quantity":
        data["quantity"] = text
        data["step"] = "date_in"
        await update.message.reply_text("📅 Введите дату сдачи:")

    elif data["step"] == "date_in":
        data["date_in"] = text
        data["step"] = "ready_in"
        await update.message.reply_text("⌛ Через сколько дней будет готово?")

    elif data["step"] == "ready_in":
        data["ready_in"] = text
        data["step"] = "paid"
        await update.message.reply_text("💰 Оплата произведена? (да / нет):")

    elif data["step"] == "paid":
        data["paid"] = text.lower()
        data["step"] = "done"

        order_id = generate_order_id()
        days = int(data["ready_in"])
        ready_date = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%d.%m.%Y")
        total = int(data["price"].replace(" ", "")) * int(data["quantity"])

        sheet.append_row([
            order_id,
            data["phone"],
            data["items"],
            data["date_in"],
            days,
            data["paid"],
            ready_date,
            "отправлено",
            total
        ])

        msg = (
            f"🧾 Ваш заказ принят!\n"
            f"🆔 ID: {order_id}\n"
            f"📅 Дата сдачи: {data['date_in']}\n"
            f"⌛ Готово будет: {ready_date}\n"
            f"💰 Статус оплаты: {'✅ Оплачено' if data['paid'] == 'да' else '❌ Не оплачено'}\n"
            f"💵 Стоимость: {total:,} сум\n"
            f"Спасибо, что выбрали Diamond Cleaning!"
        )
        await update.message.reply_text(msg)

# === Ежемесячный отчет ===
async def send_monthly_report(context: CallbackContext):
    values = sheet.get_all_values()[1:]
    client_count = len(values)
    item_count = 0
    total_sum = 0
    paid_sum = 0

    for row in values:
        try:
            qty = int(row[4])
            total = int(row[8])
            item_count += qty
            total_sum += total
            if 'да' in row[5].lower():
                paid_sum += total
        except:
            continue

    unpaid = total_sum - paid_sum
    text = (
        f"📊 Ежемесячный отчет за Diamond Cleaning\n\n"
        f"👥 Клиентов: {client_count}\n🧺 Всего вещей: {item_count}\n💵 Общая сумма: {total_sum:,} сум\n"
        f"✅ Оплачено: {paid_sum:,} сум\n❗ Осталось: {unpaid:,} сум"
    )
    await context.bot.send_message(chat_id=1253874719, text=text)

# === Планировщик ===
scheduler = AsyncIOScheduler()
scheduler.add_job(send_monthly_report, CronTrigger(day=1, hour=7, minute=0), args=[None])
scheduler.start()

# === Запуск ===
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
app.add_handler(MessageHandler(filters.TEXT & (filters.Regex("📍 Узнать локацию") | filters.Regex("🏬 Наши филиалы")), handle_buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == '__main__':
    print("🤖 Бот запущен и разделяет клиентов и сотрудников...")
    app.run_polling()
