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

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define states for conversation
CHOOSE_ACTION, GET_RECOMMENDATION_INPUT, GET_KEYWORD_SEARCH_INPUT = range(3)

# Load tools data from JSON file
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
    """
    Sends user's request to Groq API to extract relevant keywords.
    """
    try:
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            logger.error("GROQ_API_KEY environment variable not set.")
            return []

        client = Groq(api_key=groq_api_key)
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
        # The model might wrap the list in a dictionary, e.g., {"keywords": [...]}. Let's handle that.
        response_data = json.loads(response_content)
        
        if isinstance(response_data, dict):
            # Look for a key that contains a list
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
    """
    Finds tools in the database that match the given keywords.
    """
    if not keywords or not tools_db:
        return []

    scores = {tool['name']: 0 for tool in tools_db}
    
    for tool in tools_db:
        for keyword in keywords:
            if keyword.lower() in tool['name'].lower() or \
               keyword.lower() in tool['description'].lower() or \
               keyword.lower() in " ".join(tool['keywords']).lower():
                scores[tool['name']] += 1

    # Filter out tools with a score of 0
    scored_tools = [tool for tool in tools_db if scores[tool['name']] > 0]
    
    # Sort tools by score in descending order
    sorted_tools = sorted(scored_tools, key=lambda t: scores[t['name']], reverse=True)
    
    return sorted_tools[:3] # Return top 3 matches


def search_by_keyword(keyword: str) -> list:
    """
    Directly searches for a tool by a single keyword.
    """
    if not keyword or not tools_db:
        return []
    
    keyword = keyword.lower()
    matched_tools = []
    for tool in tools_db:
        if keyword in tool['name'].lower() or \
           keyword in tool['description'].lower() or \
           keyword in " ".join(tool['keywords']).lower():
            matched_tools.append(tool)
            
    return matched_tools[:5] # Return top 5 matches


# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and shows the main menu."""
    reply_keyboard = [
        ["🧠 המלצה חכמה"],
        ["🔍 חיפוש מהיר לפי מילת מפתח"],
        ["❓ עזרה"],
    ]
    
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
        
    elif user_choice == "🔍 חיפוש מהיר לפי מילת מפתח":
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
        return await start(update, context) # Restart

    logger.info(f"Groq keywords for '{user_text}': {keywords}")
    
    recommended_tools = find_tools(keywords)
    
    if not recommended_tools:
        await update.message.reply_text(
            "לא מצאתי כלי שמתאים בדיוק לבקשה שלך במאגר שלי.\n"
            "אולי ננסה חיפוש עם מילות מפתח אחרות?"
        )
    else:
        message = "✨ מצאתי כמה כלים שיכולים להתאים לך:\n\n"
        for tool in recommended_tools:
            message += f"🧠 ***{tool['name']}***\n"
            message += f"*{tool['description']}*\n"
            message += f"🔗 [קישור לכלי]({tool['url']})\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

    # End conversation and show main menu again
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
            message += f"***{tool['name']}***\n"
            message += f"*{tool['description']}*\n"
            message += f"🔗 [קישור לכלי]({tool['url']})\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

    # End conversation and show main menu again
    return await start(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays a help message."""
    await update.message.reply_text(
        "***איך משתמשים בבוט?***\n\n"
        "🔹 **המלצה חכמה**: תאר לי מה אתה צריך, ואני אשתמש בבינה מלאכותית כדי למצוא את הכלים המתאימים ביותר מהמאגר שלי.\n\n"
        "🔹 **חיפוש מהיר**: אם אתה יודע מה אתה מחפש, הקלד מילת מפתח (כמו 'וידאו' או 'שיווק') ואציג לך את כל הכלים הרלוונטיים.\n\n"
        "בכל שלב, אפשר להתחיל מחדש עם הפקודה /start.",
        parse_mode='Markdown'
    )
    return await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text(
        "הפעולה בוטלה. חוזרים לתפריט הראשי.", reply_markup=ReplyKeyboardRemove()
    )
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
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    # Start the keep-alive server in a separate thread
    keep_alive_thread = threading.Thread(target=run_keep_alive_server, daemon=True)
    keep_alive_thread.start()
    
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(bot_token).build()

    # Setup conversation handler
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
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
