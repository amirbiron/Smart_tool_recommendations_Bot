import os
import logging
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

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
    if not MONGO_URI:
        logger.warning("MONGO_URI not set. User stats feature will be disabled.")
    else:
        client = MongoClient(MONGO_URI)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        db = client.smart_tools_bot_db
        logger.info("Successfully connected to MongoDB.")
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
    """Loads the tools database from a JSON file."""
    try:
        with open('tools.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading tools.json: {e}")
        return []

tools_db = load_tools()

# --- Groq API Integration ---
def get_keywords_from_groq(user_text: str) -> list:
    """Sends user's request to Groq API to extract relevant keywords."""
    try:
        if not GROQ_API_KEY:
            logger.error("GROQ_API_KEY environment variable not set.")
            return []

        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Your task is to extract relevant keywords from the user's request for a tool. Respond ONLY with a JSON array of 3-5 Hebrew keywords. For example, for 'אני צריך משהו לכתוב ולארגן רעיונות', your response should be '[\"כתיבה\", \"ארגון\", \"רעיונות\", \"פרודוקטיביות\"]'. Do not add any other text.",
                },
                {
                    "role": "user",
                    "content": user_text,
                },
            ],
            model="llama3-8b-8192",
            temperature=0.2,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        
        response_content = chat_completion.choices[0].message.content
        response_data = json.loads(response_content)
        
        if isinstance(response_data, dict):
            for key, value in response_data.items():
                if isinstance(value, list):
                    return value
        elif isinstance(response_data, list):
            return response_data
            
        logger.warning(f"Groq returned unexpected JSON structure: {response_content}")
        return []

    except Exception as e:
        logger.error(f"Error calling Groq API: {e}")
        return []

# --- Search Logic ---
def find_tools(keywords: list) -> list:
    """Finds tools in the database that match the given keywords."""
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
    """Directly searches for a tool by a single keyword."""
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
    """Starts the conversation, saves the user, and shows the main menu."""
    user = update.message.from_user
    logger.info(f"User {user.first_name} (ID: {user.id}) started the bot.")

    # --- MongoDB: Save User ---
    if db:
        try:
            users_collection = db.users
            users_collection.update_one(
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
    """Handles the user's choice from the main menu."""
    user_choice = update.message.text
    if user_choice == "🧠 המלצה חכמה":
        await update.message.reply_text(
            "מעולה! תאר לי במילים שלך איזה כלי אתה מחפש.\n"
            "לדוגמה: 'אני צריך כלי פשוט לארגן רעיונות וכתיבה אישית'",
            reply_markup=ReplyKeyboardRemove(),
        )
        return GET_RECOMMENDATION_INPUT
    elif user_choice == "🔍 חיפוש מהיר":
        await update.message.reply_text(
            "בטח, הקלד מילת מפתח לחיפוש (למשל: 'וידאו', 'אוטומציה', 'Notion').",
            reply_markup=ReplyKeyboardRemove(),
        )
        return GET_KEYWORD_SEARCH_INPUT
    elif user_choice == "❓ עזרה":
        return await help_command(update, context)
    else:
        await update.message.reply_text("לא הבנתי את הבחירה. אנא בחר מהכפתורים.")
        return CHOOSE_ACTION

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets user input, finds tools via Groq, and returns them."""
    user_text = update.message.text
    await update.message.reply_text("קיבלתי. בודק לך מול המאגר החכם... 🤖")
    keywords = get_keywords_from_groq(user_text)
    if not keywords:
        await update.message.reply_text("מצטער, לא הצלחתי להבין את הבקשה. אולי ננסח מחדש?")
        return await start(update, context)
    logger.info(f"Groq keywords for '{user_text}': {keywords}")
    recommended_tools = find_tools(keywords)
    if not recommended_tools:
        await update.message.reply_text("לא מצאתי כלי שמתאים בדיוק לבקשה שלך במאגר שלי.")
    else:
        message = "✨ מצאתי כמה כלים שיכולים להתאים לך:\n\n"
        for tool in recommended_tools:
            message += f"🧠 ***{tool['name']}***\n*{tool['description']}*\n🔗 [קישור לכלי]({tool['url']})\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    return await start(update, context)

async def keyword_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Searches for tools based on a single keyword."""
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
    """Displays a help message."""
    await update.message.reply_text(
        "***איך משתמשים בבוט?***\n\n"
        "🔹 **המלצה חכמה**: תאר לי מה אתה צריך, ואני אשתמש בבינה מלאכותית כדי למצוא את הכלים המתאימים ביותר.\n\n"
        "🔹 **חיפוש מהיר**: הקלד מילת מפתח ואציג לך את כל הכלים הרלוונטיים.\n\n"
        "בכל שלב, אפשר להתחיל מחדש עם הפקודה /start.",
        parse_mode='Markdown'
    )
    return await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to get user count."""
    user_id = str(update.message.from_user.id)
    if not ADMIN_ID or user_id != ADMIN_ID:
        logger.warning(f"Unauthorized stats access attempt by user {user_id}.")
        return
    if not db:
        await update.message.reply_text("חיבור ל-MongoDB לא הוגדר.")
        return
    try:
        user_count = db.users.count_documents({})
        await update.message.reply_text(f"📊 סך הכל משתמשים ייחודיים בבוט: {user_count}")
    except Exception as e:
        await update.message.reply_text(f"שגיאה בקבלת נתונים מ-MongoDB: {e}")
        logger.error(f"Error fetching stats from MongoDB: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("הפעולה בוטלה. חוזרים לתפריט הראשי.", reply_markup=ReplyKeyboardRemove())
    return await start(update, context)

# --- Keep-Alive Server ---
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive")

def run_keep_alive_server():
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, KeepAliveHandler)
    logger.info("Keep-alive server started on port 8080")
    httpd.serve_forever()

# --- Main Application Setup ---
def main() -> None:
    """Run the bot."""
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    keep_alive_thread = threading.Thread(target=run_keep_alive_server, daemon=True)
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
    application.add_handler(CommandHandler("stats", stats_command)) # Add the new stats command
    
    application.run_polling()

if __name__ == "__main__":
    main()
