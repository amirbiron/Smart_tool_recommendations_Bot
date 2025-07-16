import os
import logging
import json
import threading
from dotenv import load_dotenv
import requests
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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = os.getenv("ADMIN_ID")
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
CUSTOM_SEARCH_ENGINE_ID = os.getenv("CUSTOM_SEARCH_ENGINE_ID")

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

CHOOSE_ACTION, GET_RECOMMENDATION_INPUT = range(2)

# --- Load all necessary data on startup ---
def load_all_data():
    try:
        logger.info("Loading tools.json...")
        with open('tools.json', 'r', encoding='utf-8') as f:
            tools_db = json.load(f)
        
        logger.info("Loading Faiss index (tools.faiss)...")
        vector_index = faiss.read_index('tools.faiss')

        logger.info("Loading index-to-name mapping...")
        with open('index_to_name.json', 'r', encoding='utf-8') as f:
            index_to_name = json.load(f)
            # JSON saves keys as strings, convert them back to int
            index_to_name = {int(k): v for k, v in index_to_name.items()}

        logger.info("Loading SentenceTransformer model...")
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        logger.info("All data loaded successfully.")
        return tools_db, vector_index, index_to_name, embedding_model
    except Exception as e:
        logger.critical(f"FATAL: Could not load essential data files: {e}")
        logger.critical("Please run 'create_embeddings.py' first.")
        return None, None, None, None

tools_db, vector_index, index_to_name, embedding_model = load_all_data()

# ==============================================================================
# ===== Vector Search + Reranking Architecture =====
# ==============================================================================

def find_candidates_with_vector_search(user_query: str, k=15) -> list:
    """
    Step 1: Use vector search to find the top-k most similar tools.
    """
    if vector_index is None or embedding_model is None:
        return []
    
    logger.info(f"Creating embedding for query: '{user_query}'")
    query_embedding = embedding_model.encode([user_query])
    query_embedding = np.array(query_embedding).astype('float32')
    
    logger.info(f"Searching Faiss index for top {k} candidates...")
    distances, indices = vector_index.search(query_embedding, k)
    
    candidate_names = [index_to_name[i] for i in indices[0]]
    candidate_tools = [tool for tool in tools_db if tool['name'] in candidate_names]
    
    logger.info(f"Found {len(candidate_tools)} candidates via vector search.")
    return candidate_tools

def rerank_candidates_semantically(candidates: list, user_query: str) -> list:
    """
    Step 2: Sends the candidate list to Groq for semantic reranking.
    """
    if not candidates:
        return []

    logger.info("Performing semantic reranking on candidates...")
    candidates_string = json.dumps(candidates, ensure_ascii=False)
    try:
        if not GROQ_API_KEY: return []
        client = Groq(api_key=GROQ_API_KEY)
        system_prompt = (
            "You are a smart recommendation engine. Your task is to analyze the user's request and find the best matching tools from a pre-filtered list of candidates. "
            "Return a JSON object with a single key, 'best_matches', containing a list of the names of the top 1-3 most relevant tools from the candidate list. "
            "If no tools are a good match, return an empty list."
        )
        user_prompt = (
            f"User's request: \"{user_query}\"\n\n"
            f"Here is the pre-filtered list of candidate tools:\n{candidates_string}"
        )
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model="llama3-70b-8192",
            temperature=0.1, max_tokens=200,
            response_format={"type": "json_object"},
        )
        response_content = chat_completion.choices[0].message.content
        logger.info(f"Semantic reranking response from Groq: {response_content}")
        data = json.loads(response_content)
        return data.get("best_matches", [])
    except Exception as e:
        logger.error(f"Error in rerank_candidates_semantically: {e}")
        return []

# --- Other functions (Price Check, etc.) ---
def get_price_from_groq(tool_name: str) -> str:
    # ... (code remains the same)
    logger.info(f"Fetching price for tool: {tool_name}")
    try:
        if not GROQ_API_KEY: return "לא ניתן היה לבדוק את המחיר."
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": f"What is the current basic pricing for the tool '{tool_name}'? Search the web for its official pricing page. Respond ONLY with a short, concise answer in Hebrew. If you cannot find the price, say 'לא הצלחתי למצוא מחיר עדכני'. Do not add any introductory text."},
            ],
            model="llama3-70b-8192",
            temperature=0.2, max_tokens=200,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error fetching price for {tool_name}: {e}")
        return "אירעה שגיאה בעת בדיקת המחיר."

def find_tool_by_name(name: str) -> dict | None:
    # ... (code remains the same)
    for tool in tools_db:
        if tool['name'].lower() == name.lower():
            return tool
    return None

async def send_tool_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE, tool: dict):
    # ... (code remains the same)
    keyboard = [[InlineKeyboardButton("💰 בדוק מחיר עדכני", callback_data=f"price_check:{tool['name']}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"🧠 ***{tool['name']}***\n*{tool.get('description', 'No description available.')}*\n🔗 [קישור לכלי]({tool.get('url', '#')})\n"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, parse_mode='Markdown', reply_markup=reply_markup)

async def price_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code remains the same)
    query = update.callback_query
    await query.answer()
    tool_name = query.data.split(':', 1)[1]
    original_message = query.message.text
    context.user_data[f"tool_{tool_name}"] = {"text": original_message, "markup": query.message.reply_markup}
    await query.edit_message_text(text=f"בודק מחיר עדכני עבור *{tool_name}*...", parse_mode='Markdown')
    price_info = get_price_from_groq(tool_name)
    keyboard = [[InlineKeyboardButton("🔙 חזור למידע על הכלי", callback_data=f"back_to_tool:{tool_name}")]]
    await query.edit_message_text(text=f"💰 מידע על תמחור עבור *{tool_name}*:\n\n{price_info}", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def back_to_tool_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code remains the same)
    query = update.callback_query
    await query.answer()
    tool_name = query.data.split(':', 1)[1]
    original_data = context.user_data.get(f"tool_{tool_name}")
    if original_data:
        await query.edit_message_text(text=original_data["text"], reply_markup=original_data["markup"], parse_mode='Markdown')
    else:
        await query.edit_message_text(text="אירעה שגיאה. לא נמצא המידע המקורי.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (code remains the same)
    user = update.message.from_user
    logger.info(f"User {user.first_name} (ID: {user.id}) started the bot.")
    if db is not None:
        try:
            db.users.update_one({'_id': user.id}, {'$setOnInsert': {'first_name': user.first_name, 'username': user.username}}, upsert=True)
        except Exception as e:
            logger.error(f"Failed to save user {user.id} to MongoDB: {e}")
    reply_keyboard = [["🧠 המלצה חכמה"]]
    await update.message.reply_text("👋 שלום!\nאני בוט המלצות חכם. תאר לי מה אתה צריך ואמצא לך את הכלי המתאים ביותר.", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # ... (code remains the same)
    user_choice = update.message.text
    if user_choice == "🧠 המלצה חכמה":
        await update.message.reply_text("מעולה! תאר לי במילים שלך, כמה שיותר בפירוט, איזה כלי אתה מחפש...", reply_markup=ReplyKeyboardRemove())
        return GET_RECOMMENDATION_INPUT
    return CHOOSE_ACTION

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_text = update.message.text
    await update.message.reply_text("קיבלתי. מבצע חיפוש סמנטי במאגר... 🤖")
    
    # Step 1: Find candidates using vector search
    candidate_tools = find_candidates_with_vector_search(user_text)
    
    # Step 2: Rerank candidates with a powerful LLM
    recommended_tool_names = rerank_candidates_semantically(candidate_tools, user_text)
    
    if recommended_tool_names:
        await update.message.reply_text("✨ אלו הכלים שמצאתי שהכי מתאימים לבקשה שלך:")
        for tool_name in recommended_tool_names:
            tool = find_tool_by_name(tool_name)
            if tool:
                await send_tool_recommendation(update, context, tool)
    else:
        await update.message.reply_text("מצטער, לא מצאתי התאמה טובה במאגר שלי. אולי נסה לנסח את הבקשה קצת אחרת?")
    
    return await start(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (code remains the same)
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

# --- Flask and Main App Setup (remains the same) ---
flask_app = Flask(__name__)
@flask_app.route('/')
def health_check():
    return "Bot is alive and kicking!"

def run_flask_app():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def main() -> None:
    if not all([tools_db, vector_index, index_to_name, embedding_model]):
        logger.critical("Bot cannot start due to missing data files. Exiting.")
        return
        
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
