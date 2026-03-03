import os
import logging
import json
import io
import csv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import db as db_mod
import google_sheets as sheets
import ai_service as ai
from dotenv import load_dotenv

load_dotenv()

database = db_mod.Database()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


async def send_table_as_csv(update: Update, sheet_id, sheet_name):
    """Генерирует CSV из данных листа и отправляет пользователю."""
    try:
        data = sheets.get_sheet_data(sheet_id, f"{sheet_name}!A:Z")
        if not data:
            await (update.message or update.callback_query.message).reply_text(f"Лист '{sheet_name}' пуст.")
            return

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(data)
        output.seek(0)
        
        byte_output = io.BytesIO(output.getvalue().encode('utf-8-sig'))
        byte_output.name = f"{sheet_name}.csv"
        
        target = update.message or update.callback_query.message
        await target.reply_document(document=byte_output, filename=f"{sheet_name}.csv", caption=f"Выгрузка листа: {sheet_name}")
    except Exception as e:
        logging.error(f"CSV Error: {e}")
        await (update.message or update.callback_query.message).reply_text("Ошибка при создании CSV. Проверь название листа.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    database.save_session({'userId': user_id, 'state': 'START'})
    await update.message.reply_text(
        "Привет! Я твой ассистент по выбору курсов в магистратуре AITH.\n\n"
        "1. Пришли ссылку на Google Таблицу.\n"
        "2. Я найду курсы и расписание.\n"
        "3. Могу выгрузить данные в CSV (просто напиши 'скинь csv')."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    original_text = update.message.text
    lower_text = original_text.lower()
    user_id = update.effective_user.id
    session = database.get_session(user_id)
    
    if not session:
        session = {'userId': user_id, 'state': 'START'}
        database.save_session(session)

    if 'docs.google.com/spreadsheets' in original_text:
        sheet_id = sheets.extract_sheet_id(original_text)
        if sheet_id:
            session['sheetUrl'] = original_text
            session['state'] = 'AWAITING_LINK_CONFIRMATION'
            database.save_session(session)
            
            keyboard = [
                [InlineKeyboardButton("✅ Да, всё верно", callback_data='confirm_link')],
                [InlineKeyboardButton("❌ Нет, другая ссылка", callback_data='cancel_link')]
            ]
            await update.message.reply_text(
                f"Я распознал таблицу. Подтверждаешь привязку?\n{original_text}", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    # Логика запросов
    if session.get('state') == 'CHOOSING_COURSES' and session.get('sheetUrl'):
        sheet_id = sheets.extract_sheet_id(session['sheetUrl'])
        
        # Команды на CSV
        if "выгрузи" in lower_text or "csv" in lower_text:
            sheet_to_export = "Расписание" if "расписание" in lower_text else "Таблица выбора"
            await send_table_as_csv(update, sheet_id, sheet_to_export)
            return

        # Запрос к ИИ
        await update.message.reply_text("Ищу информацию в таблицах...")
        try:
            course_data = sheets.get_sheet_data(sheet_id, "Таблица выбора!A:Z")
            schedule_data = sheets.get_sheet_data(sheet_id, "Расписание!A:Z")
            
            ai_response = ai.process_user_request(original_text, {
                'sheetData': course_data,
                'scheduleData': schedule_data,
                'userName': update.effective_user.first_name
            })
            await update.message.reply_text(ai_response)
        except Exception as e:
            logging.error(f"AI Error: {e}")
            await update.message.reply_text("Не удалось получить данные. Проверь доступ бота к таблице.")
    else:
        if session.get('state') == 'START':
            await update.message.reply_text("Пришли, пожалуйста, ссылку на таблицу.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    session = database.get_session(user_id)
    
    if not session: return

    if query.data == 'confirm_link':
        session['state'] = 'CHOOSING_COURSES'
        database.save_session(session)
        await query.answer("Таблица привязана!")
        await query.edit_message_text("Отлично! Теперь я готов отвечать на вопросы о курсах (строки 5-6) и расписании.")
        
    elif query.data == 'cancel_link':
        session['state'] = 'START'
        session['sheetUrl'] = None
        database.save_session(session)
        await query.answer("Отменено")
        await query.edit_message_text("Без проблем. Пришли верную ссылку, когда будешь готов.")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logging.error("Токен бота не найден!")
        return

    application = ApplicationBuilder().token(token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
        
    logging.info("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()