import os
import logging
import json
import threading
from dotenv import load_dotenv
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
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

# --- Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")

# --- Paths for pre-built files (loaded from the repo) ---
TOOLS_JSON_PATH = 'tools.json' 
FAISS_INDEX_PATH = 'tools.faiss'
MAPPING_PATH = 'index_to_name.json'

# --- Global variables for loaded data ---
tools_db = []
vector_index = None
index_to_name = {}
embedding_model = None

# --- Define states for conversation ---
CHOOSE_ACTION, GET_RECOMMENDATION_INPUT = range(2)

def load_all_data():
    global tools_db, vector_index, index_to_name, embedding_model
    try:
        logger.info("Loading tools.json...")
        with open(TOOLS_JSON_PATH, 'r', encoding='utf-8') as f:
            tools_db = json.load(f)
        
        logger.info(f"Loading Faiss index from {FAISS_INDEX_PATH}...")
        vector_index = faiss.read_index(FAISS_INDEX_PATH)

        logger.info(f"Loading index-to-name mapping from {MAPPING_PATH}...")
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            index_to_name = json.load(f)
            index_to_name = {int(k): v for k, v in index_to_name.items()}
        
        logger.info("Loading SentenceTransformer model...")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        logger.info("All data loaded successfully.")
    except Exception as e:
        logger.critical(f"FATAL: Could not load essential data files: {e}. Please ensure tools.faiss and index_to_name.json are in your GitHub repository.")
        vector_index = None

def find_candidates_with_vector_search(user_query: str, k=15) -> list:
    if vector_index is None or embedding_model is None:
        logger.error("Vector index or model not loaded. Cannot perform search.")
        return []
    
    query_embedding = embedding_model.encode([user_query])
    query_embedding = np.array(query_embedding).astype('float32')
    
    try:
        _, indices = vector_index.search(query_embedding, k)
        candidate_names = [index_to_name.get(str(i)) for i in indices[0]]
        return [tool for tool in tools_db if tool and tool.get('name') in candidate_names]
    except Exception as e:
        logger.error(f"Error during Faiss search: {e}")
        return []

def rerank_candidates_semantically(candidates: list, user_query: str) -> list:
    if not candidates: return []
    candidates_string = json.dumps(candidates, ensure_ascii=False)
    try:
        if not GROQ_API_KEY: return []
        client = Groq(api_key=GROQ_API_KEY)
        system_prompt = "You are a smart recommendation engine. Analyze the user's request and find the best matching tools from a pre-filtered list of candidates. Return a JSON object: {\"best_matches\": [\"ToolName1\", \"ToolName2\"]}. If no tools are a good match, return an empty list."
        user_prompt = f"User's request: \"{user_query}\"\n\nCandidate tools:\n{candidates_string}"
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model="llama3-70b-8192", temperature=0.1, max_tokens=200, response_format={"type": "json_object"}
        )
        data = json.loads(chat_completion.choices[0].message.content)
        return data.get("best_matches", [])
    except Exception as e:
        logger.error(f"Error in rerank_candidates_semantically: {e}")
        return []

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not vector_index:
        await update.message.reply_text("מצטער, המאגר שלי נמצא בתחזוקה. אנא נסה שוב מאוחר יותר.")
        return await start(update, context)

    user_text = update.message.text
    await update.message.reply_text("קיבלתי. מבצע חיפוש סמנטי במאגר... 🤖")
    
    candidate_tools = find_candidates_with_vector_search(user_text)
    recommended_tool_names = rerank_candidates_semantically(candidate_tools, user_text)
    
    if recommended_tool_names:
        await update.message.reply_text("✨ אלו הכלים שמצאתי שהכי מתאימים לבקשה שלך:")
        for tool_name in recommended_tool_names:
            tool = find_tool_by_name(tool_name)
            if tool:
                await send_tool_recommendation(update, context, tool)
    else:
        await update.message.reply_text("מצטער, לא מצאתי התאמה טובה במאגר שלי.")
    
    return await start(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [["🧠 המלצה חכמה"]]
    await update.message.reply_text("👋 שלום!\nאני בוט המלצות חכם. תאר לי מה אתה צריך ואמצא לך את הכלי המתאים ביותר.", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_choice = update.message.text
    if user_choice == "🧠 המלצה חכמה":
        await update.message.reply_text("מעולה! תאר לי במילים שלך, כמה שיותר בפירוט, איזה כלי אתה מחפש...", reply_markup=ReplyKeyboardRemove())
        return GET_RECOMMENDATION_INPUT
    return CHOOSE_ACTION

def find_tool_by_name(name: str) -> dict | None:
    for tool in tools_db:
        if tool['name'].lower() == name.lower():
            return tool
    return None

async def send_tool_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE, tool: dict):
    keyboard = [[InlineKeyboardButton("💰 בדוק מחיר עדכני", callback_data=f"price_check:{tool['name']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"🧠 ***{tool['name']}***\n*{tool.get('description', 'No description available.')}*\n🔗 [קישור לכלי]({tool.get('url', '#')})\n"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, parse_mode='Markdown', reply_markup=reply_markup)

async def price_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code for price check)
    pass

async def back_to_tool_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code for back button)
    pass

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code for stats)
    pass

flask_app = Flask(__name__)
@flask_app.route('/')
def health_check():
    return "Bot is alive and kicking!"

def run_flask_app():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def main() -> None:
    load_all_data()

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
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(price_check_callback, pattern=r"^price_check:"))
    application.add_handler(CallbackQueryHandler(back_to_tool_callback, pattern=r"^back_to_tool:"))
    
    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
