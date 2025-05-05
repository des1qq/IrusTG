import logging
import asyncio
from datetime import datetime, timedelta
import csv
import os
import aiohttp
import nest_asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === Настройки ===
TOKEN = BOT_TOKEN
CHAT_ID = 6093665080
FETCH_INTERVAL = 160  # интервал запроса в секундах
SENSITIVITY = 0.4     # чувствительность в %
LOG_FILE = "moex_data.csv"

# === Логирование ===
logging.basicConfig(
    filename='bot.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === История и состояние ===
data_history = []
last_alert_times = {"noon": None, "close": None}

# === CSV логирование ===
def log_to_csv(timestamp, price):
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['timestamp', 'price'])
        writer.writerow([timestamp.isoformat(), price])

# === Получение данных с MOEX ===
async def get_moex_index():
    url = 'https://iss.moex.com/iss/engines/stock/markets/index/securities/IRUS.json'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    board_data = data['marketdata']['data'][0]
    return {
        'close': board_data[8],
        'low': board_data[9],
        'high': board_data[10],
        'prev_close': board_data[12]
    }

# === Отправка сообщений ===
async def send_alert(bot, current, low, high, prev):
    message = (
        f"IRUS Index Movement Alert!\n\n"
        f"Current Price: {current}\n"
        f"Today's Low: {low}\n"
        f"Today's High: {high}\n"
        f"Yesterday's Close: {prev}"
    )
    await bot.send_message(chat_id=CHAT_ID, text=message)
    logging.info("Sent alert")

async def send_regular_update(bot, time_label, index_data):
    message = (
        f"Regular Update ({time_label}):\n\n"
        f"Current Price: {index_data['close']}\n"
        f"Today's Low: {index_data['low']}\n"
        f"Today's High: {index_data['high']}\n"
        f"Yesterday's Close: {index_data['prev_close']}"
    )
    await bot.send_message(chat_id=CHAT_ID, text=message)
    logging.info(f"Sent regular update for {time_label}")

# === Основной цикл ===
async def monitor_loop(application: Application):
    global data_history, last_alert_times

    while True:
        try:
            index_data = await get_moex_index()
            current_time = datetime.utcnow()
            current_price = index_data['close']

            data_history.append({'time': current_time, 'price': current_price})
            data_history = [d for d in data_history if d['time'] > current_time - timedelta(hours=1)]
            log_to_csv(current_time, current_price)

            prices = [d['price'] for d in data_history]
            if prices:
                percent_change = abs((current_price - prices[0]) / prices[0]) * 100
                if percent_change >= SENSITIVITY:
                    await send_alert(application.bot, current_price, index_data['low'], index_data['high'], index_data['prev_close'])
                    data_history = []

            local_time = current_time + timedelta(hours=4)  # UTC+4
            current_hour = local_time.hour
            current_minute = local_time.minute

            if current_hour == 12 and current_minute == 0:
                if not last_alert_times['noon'] or (local_time - last_alert_times['noon']).seconds > 3600:
                    await send_regular_update(application.bot, 'Noon (12:00)', index_data)
                    last_alert_times['noon'] = local_time

            if current_hour == 18 and current_minute == 40:
                if not last_alert_times['close'] or (local_time - last_alert_times['close']).seconds > 3600:
                    await send_regular_update(application.bot, 'Before Close (18:40)', index_data)
                    last_alert_times['close'] = local_time

            await asyncio.sleep(FETCH_INTERVAL)

        except Exception as e:
            logging.error(f"Error in monitor loop: {e}")
            await asyncio.sleep(FETCH_INTERVAL)

# === Команды ===
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        index_data = await get_moex_index()
        text = (
            f"IRUS Index Status:\n\n"
            f"Current Price: {index_data['close']}\n"
            f"Today's Low: {index_data['low']}\n"
            f"Today's High: {index_data['high']}\n"
            f"Yesterday's Close: {index_data['prev_close']}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(" Failed to fetch data.")
        logging.error(f"Error in /status command: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/status — Текущий индекс IRUS\n"
        "/help — Список команд\n"

    )

# === Главная точка входа ===
async def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))

    asyncio.create_task(monitor_loop(application))
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
