import os
import logging
import json
import threading
from dotenv import load_dotenv

from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from groq import Groq
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = os.getenv("ADMIN_ID")

db = None
try:
    if MONGO_URI:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        db = client.smart_tools_bot_db
        logger.info("Successfully connected to MongoDB.")
    else:
        logger.warning("MONGO_URI not set. User stats feature will be disabled.")
except Exception as e:
    logger.error(f"An error occurred with MongoDB setup: {e}")
    db = None

# States for conversation
CHOOSE_ACTION, GET_RECOMMENDATION_INPUT, GET_KEYWORD_SEARCH_INPUT = range(3)

def load_tools():
    try:
        with open('tools.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading tools.json: {e}")
        return []

tools_db = load_tools()

def get_keywords_from_groq(user_text: str) -> list:
    try:
        if not GROQ_API_KEY: return []
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an expert in keyword extraction. Respond ONLY with a valid JSON object: {\"keywords\": [\"keyword1\", \"keyword2\"]}. The keywords should be in Hebrew."},
                {"role": "user", "content": user_text},
            ],
            model="llama3-8b-8192",
            temperature=0.1, max_tokens=100,
            response_format={"type": "json_object"},
        )
        data = json.loads(chat_completion.choices[0].message.content)
        return data.get("keywords", [])
    except Exception as e:
        logger.error(f"Error in get_keywords_from_groq: {e}")
        return []

def get_price_from_groq(tool_name: str) -> str:
    """Gets the current pricing for a specific tool using Groq."""
    logger.info(f"Fetching price for tool: {tool_name}")
    try:
        if not GROQ_API_KEY: return "לא ניתן היה לבדוק את המחיר."
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": f"What is the current basic pricing for the tool '{tool_name}'? Search the web for its official pricing page. Respond with a short, concise answer in Hebrew, for example: 'התוכנית החינמית מוגבלת, תוכניות בתשלום מתחילות ב-$10 לחודש.' or 'הכלי הינו בתשלום בלבד, החל מ-$29 לחודש.'. If you cannot find the price, say 'לא הצלחתי למצוא מחיר עדכני'.",
                },
            ],
            model="llama3-70b-8192",
            temperature=0.2,
            max_tokens=100,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error fetching price for {tool_name}: {e}")
        return "אירעה שגיאה בעת בדיקת המחיר."

def find_tools_in_db(keywords: list) -> list:
    if not keywords or not tools_db: return []
    scores = {tool['name']: 0 for tool in tools_db}
    for tool in tools_db:
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if 'category' in tool and keyword_lower in tool['category'].lower(): scores[tool['name']] += 3
            if keyword_lower in tool['name'].lower(): scores[tool['name']] += 2
            if 'keywords' in tool and any(keyword_lower in k.lower() for k in tool['keywords']): scores[tool['name']] += 1
            if 'description' in tool and keyword_lower in tool['description'].lower(): scores[tool['name']] += 0.5
    scored_tools = [tool for tool in tools_db if scores[tool['name']] > 0]
    return sorted(scored_tools, key=lambda t: scores[t['name']], reverse=True)[:3]

def search_by_keyword(keyword: str) -> list:
    return find_tools_in_db([keyword])

async def send_tool_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE, tool: dict):
    """Sends a formatted message for a single tool with an inline button."""
    keyboard = [[
        InlineKeyboardButton("💰 בדוק מחיר עדכני", callback_data=f"price_check:{tool['name']}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = f"🧠 ***{tool['name']}***\n"
    message += f"*{tool.get('description', 'No description available.')}*\n"
    message += f"🔗 [קישור לכלי]({tool.get('url', '#')})\n"
    
    # Using context.bot.send_message for more flexibility
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown', reply_markup=reply_markup)


async def price_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Check Price' button click."""
    query = update.callback_query
    await query.answer()
    
    tool_name = query.data.split(':', 1)[1]
    
    await query.edit_message_text(text=f"בודק מחיר עדכני עבור *{tool_name}*...", parse_mode='Markdown')
    
    price_info = get_price_from_groq(tool_name)
    
    await query.edit_message_text(text=f"💰 מידע על תמחור עבור *{tool_name}*:\n\n{price_info}", parse_mode='Markdown')


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info(f"User {user.first_name} (ID: {user.id}) started the bot.")
    if db is not None:
        try:
            db.users.update_one(
                {'_id': user.id},
                {'$setOnInsert': {'first_name': user.first_name, 'username': user.username}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to save user {user.id} to MongoDB: {e}")

    reply_keyboard = [["🧠 המלצה חכמה"], ["🔍 חיפוש מהיר"], ["❓ עזרה"]]
    await update.message.reply_text(
        "👋 שלום!\nאני בוט המלצות שיעזור לך למצוא כלים טכנולוגיים חכמים.\n\n"
        "במה אוכל לעזור?",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_choice = update.message.text
    if user_choice == "🧠 המלצה חכמה":
        await update.message.reply_text("מעולה! תאר לי במילים שלך איזה כלי אתה מחפש...", reply_markup=ReplyKeyboardRemove())
        return GET_RECOMMENDATION_INPUT
    elif user_choice == "🔍 חיפוש מהיר":
        await update.message.reply_text("בטח, הקלד מילת מפתח לחיפוש...", reply_markup=ReplyKeyboardRemove())
        return GET_KEYWORD_SEARCH_INPUT
    elif user_choice == "❓ עזרה":
        return await help_command(update, context)
    else:
        await update.message.reply_text("לא הבנתי את הבחירה. אנא בחר מהכפתורים.")
        return CHOOSE_ACTION

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    await update.message.reply_text("קיבלתי. מבצע חיפוש במאגר המאומת שלי... 🤖")

    keywords = get_keywords_from_groq(user_text)
    recommended_tools = find_tools_in_db(keywords) if keywords else []

    if recommended_tools:
        await update.message.reply_text("✨ מצאתי כמה כלים מהמאגר שלי שמתאימים לך:")
        for tool in recommended_tools:
            await send_tool_recommendation(update, context, tool)
    else:
        await update.message.reply_text("לא מצאתי התאמה במאגר שלי. נסה לנסח מחדש או לבצע חיפוש מהיר.")
    
    return await start(update, context)

async def keyword_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyword = update.message.text
    await update.message.reply_text(f"מחפש כלים עם המילה '{keyword}' במאגר שלי...")
    
    matched_tools = search_by_keyword(keyword)

    if not matched_tools:
        await update.message.reply_text("לא מצאתי כלים התואמים למילת המפתח הזו במאגר שלי.")
    else:
        await update.message.reply_text(f"🔍 תוצאות חיפוש עבור '{keyword}':")
        for tool in matched_tools:
            await send_tool_recommendation(update, context, tool)

    return await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "***איך משתמשים בבוט?***\n\n"
        "🔹 **המלצה חכמה**: תאר לי מה אתה צריך, ואני אחפש במאגר שלי.\n\n"
        "🔹 **חיפוש מהיר**: הקלד מילת מפתח לחיפוש מהיר במאגר.\n\n"
        "לכל המלצה תוכל לבקש בדיקת מחיר עדכנית.",
        parse_mode='Markdown'
    )
    return await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if not ADMIN_ID or user_id != ADMIN_ID: return
    if db is None:
        await update.message.reply_text("חיבור ל-MongoDB לא הוגדר.")
        return
    try:
        user_count = db.users.count_documents({})
        await update.message.reply_text(f"📊 סך הכל משתמשים ייחודיים בבוט: {user_count}")
    except Exception as e:
        logger.error(f"Error fetching stats from MongoDB: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("הפעולה בוטלה.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check():
    return "Bot is alive and kicking!"

def run_flask_app():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def main() -> None:
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    keep_alive_thread = threading.Thread(target=run_flask_app, daemon=True)
    keep_alive_thread.start()
    
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            GET_RECOMMENDATION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recommendation)],
            GET_KEYWORD_SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_search)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    # === התיקון כאן ===
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(price_check_callback, pattern=r"^price_check:"))
    
    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
