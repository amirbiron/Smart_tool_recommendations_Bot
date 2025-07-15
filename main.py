import os
import logging
import json
import threading
from dotenv import load_dotenv

# --- New Imports ---
from flask import Flask

# --- Telegram and DB Imports ---
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from groq import Groq
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Load environment variables from .env file
load_dotenv()

# --- Setup Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables & Constants ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = os.getenv("ADMIN_ID")

# --- MongoDB Connection ---
db = None
try:
    if MONGO_URI:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        db = client.smart_tools_bot_db
        logger.info("Successfully connected to MongoDB.")
    else:
        logger.warning("MONGO_URI not set. User stats feature will be disabled.")
except ConnectionFailure as e:
    logger.error(f"Could not connect to MongoDB: {e}")
    db = None
except Exception as e:
    logger.error(f"An error occurred with MongoDB setup: {e}")
    db = None


# --- Define States for Conversation ---
CHOOSE_ACTION, GET_RECOMMENDATION_INPUT, GET_KEYWORD_SEARCH_INPUT = range(3)

# --- Load Tools Data ---
def load_tools():
    try:
        with open('tools.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading tools.json: {e}")
        return []

tools_db = load_tools()

# --- Groq API Functions ---
def get_keywords_from_groq(user_text: str) -> list:
    """Extracts keywords from user text for local search."""
    try:
        if not GROQ_API_KEY: return []
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert in keyword extraction. Respond ONLY with a valid JSON object: {\"keywords\": [\"keyword1\", \"keyword2\"]}.",
                },
                {"role": "user", "content": user_text},
            ],
            model="llama3-8b-8192",
            temperature=0.1, max_tokens=100,
            response_format={"type": "json_object"},
        )
        response_content = chat_completion.choices[0].message.content
        data = json.loads(response_content)
        return data.get("keywords", [])
    except Exception as e:
        logger.error(f"Error in get_keywords_from_groq: {e}")
        return []

def get_web_recommendation_from_groq(user_text: str) -> list:
    """If local search fails, this function asks Groq to search the web."""
    logger.info(f"Performing web search for: {user_text}")
    try:
        if not GROQ_API_KEY: return []
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful tech expert. The user is looking for a tool. Based on their request, recommend 1-2 tools from your knowledge base. Respond ONLY with a valid JSON object in the format: {\"recommendations\": [{\"name\": \"ToolName\", \"description\": \"...\", \"url\": \"...\"}]}. If you can't find anything, return an empty list.",
                },
                {"role": "user", "content": user_text},
            ],
            model="llama3-70b-8192",
            temperature=0.3, max_tokens=500,
            response_format={"type": "json_object"},
        )
        response_content = chat_completion.choices[0].message.content
        logger.info(f"Web search response from Groq: {response_content}")
        data = json.loads(response_content)
        return data.get("recommendations", [])
    except Exception as e:
        logger.error(f"Error in get_web_recommendation_from_groq: {e}")
        return []

# --- Search Logic ---
def find_tools_in_db(keywords: list) -> list:
    """Finds tools in the local JSON database."""
    if not keywords or not tools_db: return []
    scores = {tool['name']: 0 for tool in tools_db}
    for tool in tools_db:
        for keyword in keywords:
            if keyword.lower() in tool['name'].lower() or \
               keyword.lower() in tool['description'].lower() or \
               keyword.lower() in " ".join(tool['keywords']).lower():
                scores[tool['name']] += 1
    scored_tools = [tool for tool in tools_db if scores[tool['name']] > 0]
    sorted_tools = sorted(scored_tools, key=lambda t: scores[t['name']], reverse=True)
    return sorted_tools[:3]

def search_by_keyword(keyword: str) -> list:
    if not keyword or not tools_db: return []
    keyword = keyword.lower()
    matched_tools = [
        tool for tool in tools_db if keyword in tool['name'].lower() or \
        keyword in tool['description'].lower() or \
        keyword in " ".join(tool['keywords']).lower()
    ]
    return matched_tools[:5]

# --- Bot Handlers ---
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
        await update.message.reply_text(
            "מעולה! תאר לי במילים שלך איזה כלי אתה מחפש...",
            reply_markup=ReplyKeyboardRemove(),
        )
        return GET_RECOMMENDATION_INPUT
    elif user_choice == "🔍 חיפוש מהיר":
        await update.message.reply_text(
            "בטח, הקלד מילת מפתח לחיפוש...",
            reply_markup=ReplyKeyboardRemove(),
        )
        return GET_KEYWORD_SEARCH_INPUT
    elif user_choice == "❓ עזרה":
        return await help_command(update, context)
    else:
        await update.message.reply_text("לא הבנתי את הבחירה. אנא בחר מהכפתורים.")
        return CHOOSE_ACTION

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    await update.message.reply_text("קיבלתי. מבצע חיפוש חכם... 🤖")
    keywords = get_keywords_from_groq(user_text)
    recommended_tools = []
    if keywords:
        logger.info(f"Local search keywords for '{user_text}': {keywords}")
        recommended_tools = find_tools_in_db(keywords)

    if recommended_tools:
        message = "✨ מצאתי כמה כלים מהמאגר המאומת שלי שמתאימים לך:\n\n"
        for tool in recommended_tools:
            message += f"🧠 ***{tool['name']}***\n*{tool['description']}*\n🔗 [קישור לכלי]({tool['url']})\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        logger.info("No tools found in local DB. Falling back to web search.")
        await update.message.reply_text("לא מצאתי התאמה במאגר שלי, מבצע חיפוש רחב יותר ברשת...")
        web_tools = get_web_recommendation_from_groq(user_text)
        if web_tools:
            message = "🌐 מצאתי ברשת כמה המלצות נוספות:\n\n"
            for tool in web_tools:
                message += f"💡 ***{tool.get('name', 'N/A')}***\n"
                message += f"*{tool.get('description', 'No description available.')}*\n"
                url = tool.get('url')
                if url:
                    message += f"🔗 [קישור לכלי]({url})\n\n"
                else:
                    message += "\n"
            await update.message.reply_text(message, parse_mode='Markdown')
        else:
            await update.message.reply_text("מצטער, חיפשתי גם במאגר שלי וגם ברשת ולא מצאתי כלי מתאים לבקשה שלך.")

    return await start(update, context)


async def keyword_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyword = update.message.text
    await update.message.reply_text(f"מחפש כלים עם המילה '{keyword}'...")
    matched_tools = search_by_keyword(keyword)
    if not matched_tools:
        await update.message.reply_text("לא מצאתי כלים התואמים למילת המפתח הזו.")
    else:
        message = f"🔍 תוצאות חיפוש עבור '{keyword}':\n\n"
        for tool in matched_tools:
            message += f"***{tool['name']}***\n*{tool['description']}*\n🔗 [קישור לכלי]({tool['url']})\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    return await start(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "***איך משתמשים בבוט?***\n\n"
        "🔹 **המלצה חכמה**: תאר לי מה אתה צריך, ואני אחפש במאגר שלי. אם לא אמצא, אחפש גם ברשת.\n\n"
        "🔹 **חיפוש מהיר**: הקלד מילת מפתח לחיפוש מהיר במאגר המקומי.\n\n"
        "בכל שלב, אפשר להתחיל מחדש עם הפקודה /start.",
        parse_mode='Markdown'
    )
    return await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.message.from_user.id)
    if not ADMIN_ID or user_id != ADMIN_ID:
        logger.warning(f"Unauthorized stats access attempt by user {user_id}.")
        return
    if db is None:
        await update.message.reply_text("חיבור ל-MongoDB לא הוגדר.")
        return
    try:
        user_count = db.users.count_documents({})
        await update.message.reply_text(f"📊 סך הכל משתמשים ייחודיים בבוט: {user_count}")
    except Exception as e:
        await update.message.reply_text(f"שגיאה בקבלת נתונים מ-MongoDB: {e}")
        logger.error(f"Error fetching stats from MongoDB: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("הפעולה בוטלה. חוזרים לתפריט הראשי.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

# ==============================================================================
# ===== Keep-Alive Server using Flask (Robust Method) =====
# ==============================================================================
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    """This route is called by UptimeRobot to keep the service alive."""
    return "Bot is alive and kicking!"

def run_flask_app():
    """Runs the Flask app in a separate thread."""
    port = int(os.environ.get("PORT", 8080))
    # Use '0.0.0.0' to make sure the app is accessible from outside the container
    flask_app.run(host='0.0.0.0', port=port)

# ==============================================================================

# --- Main Application Setup ---
def main() -> None:
    """Starts the Flask app and the Telegram bot."""
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    # Start the Flask app in a background thread
    keep_alive_thread = threading.Thread(target=run_flask_app, daemon=True)
    keep_alive_thread.start()
    
    # Start the Telegram bot
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
    application.add_handler(CommandHandler("stats", stats_command))
    
    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
