#!/usr/bin/env python3
import os, logging, json, threading
from dotenv import load_dotenv
import requests
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from groq import Groq
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Environment
BOT_TOKEN    = os.getenv("BOT_TOKEN")
ADMIN_ID     = os.getenv("ADMIN_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI    = os.getenv("MONGO_URI")          # optional

# ── Paths
DATA_PATH        = os.getenv("INDEX_DIR", "/var/data")
TOOLS_JSON_PATH  = "tools.json"
FAISS_INDEX_PATH = os.path.join(DATA_PATH, "tools.faiss")
MAPPING_PATH     = os.path.join(DATA_PATH, "index_to_name.json")

# ── Globals
tools_db: list[dict] = []
vector_index = None
index_to_name: dict[int, str] = {}
embedding_model = None

# Conversation states
CHOOSE_ACTION, GET_RECOMMEND_INPUT = range(2)

# ──────────────────────────────────────────
# Loading resources
def load_all_data() -> None:
    global tools_db, vector_index, index_to_name, embedding_model
    try:
        with open(TOOLS_JSON_PATH, encoding="utf-8") as f:
            tools_db = json.load(f)

        vector_index = faiss.read_index(FAISS_INDEX_PATH)

        with open(MAPPING_PATH, encoding="utf-8") as f:
            raw = json.load(f)
            index_to_name = {int(k): v for k, v in raw.items()}

        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Resources loaded ✅")
    except Exception as e:
        logger.critical(
            "FATAL: Could not load resources (%s). "
            "Run the one-off job to create them.", e
        )
        vector_index = None  # disable search

# ──────────────────────────────────────────
# Search helpers
def find_candidates_with_vector_search(q: str, k: int = 15) -> list[dict]:
    if vector_index is None or embedding_model is None:
        return []
    emb = embedding_model.encode([q]).astype("float32")
    _, idx = vector_index.search(emb, k)
    names = {index_to_name.get(str(i)) for i in idx[0]}
    return [t for t in tools_db if t.get("name") in names]

def rerank_semantic(cands: list, q: str) -> list[str]:
    if not cands or not GROQ_API_KEY:
        return []
    client = Groq(api_key=GROQ_API_KEY)
    sys = ("You are a smart recommendation engine. "
           "Return JSON {\"best_matches\":[...]}.")
    usr = f"User: {q}\nCandidates:\n{json.dumps(cands, ensure_ascii=False)}"
    try:
        resp = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role":"system","content":sys},
                      {"role":"user","content":usr}],
            temperature=0.1,
            max_tokens=200,
            response_format={"type":"json_object"},
        )
        return json.loads(resp.choices[0].message.content).get("best_matches", [])
    except Exception as e:
        logger.error("Groq rerank error: %s", e)
        return []

def find_tool_by_name(name: str):
    return next((t for t in tools_db if t["name"].lower()==name.lower()), None)

# ──────────────────────────────────────────
# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "היי! כתוב לי מה אתה מחפש, ואמצא לך את הכלי המתאים 🤖",
        reply_markup=ReplyKeyboardRemove()
    )
    return GET_RECOMMEND_INPUT

async def choose_action(update: Update, _: ContextTypes.DEFAULT_TYPE) -> int:
    # אין תפריט פעולות – כל קלט נחשב לחיפוש
    return GET_RECOMMEND_INPUT

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if vector_index is None:
        await update.message.reply_text("המאגר בתחזוקה. נסה מאוחר יותר.")
        return ConversationHandler.END

    q = update.message.text
    await update.message.reply_text("⏳ מחפש…")

    best = rerank_semantic(find_candidates_with_vector_search(q), q)
    if best:
        await update.message.reply_text("✨ מצאתי:")
        for n in best:
            tool = find_tool_by_name(n)
            if tool:
                kb = [
                    [InlineKeyboardButton("💰 בדוק מחיר עדכני",
                                          callback_data=f"price_check:{tool['name']}")],
                    [InlineKeyboardButton("⬅️ חזור",
                                          callback_data=f"back_to_tool:{tool['name']}")]
                ]
                txt = (f"🧠 *{tool['name']}*\n"
                       f"{tool.get('description','')}\n"
                       f"[🔗 קישור]({tool.get('url','#')})")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=txt,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
    else:
        await update.message.reply_text("לא מצאתי התאמה 🙁")

    return GET_RECOMMEND_INPUT

async def price_check_callback(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Price check coming soon…")

async def back_to_tool_callback(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "כתוב בקשה חדשה או /start כדי להתחיל מחדש."
    )

async def stats_command(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text(f"Total tools loaded: {len(tools_db)}")

# ──────────────────────────────────────────
# Keep-alive Flask
flask_app = Flask(__name__)
@flask_app.route("/")
def health_check():
    return "OK"

def run_flask_app():
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# ──────────────────────────────────────────
def main() -> None:
    load_all_data()
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN not set. Exiting.")
        return

    threading.Thread(target=run_flask_app, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)
            ],
            GET_RECOMMEND_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_recommendation)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(price_check_callback, pattern=r"^price_check:"))
    app.add_handler(CallbackQueryHandler(back_to_tool_callback, pattern=r"^back_to_tool:"))

    logger.info("Polling…")
    app.run_polling()

if __name__ == "__main__":
    main()
