#!/usr/bin/env python3
# main.py – Telegram AI-tools bot

import json
import logging
import os
import threading
from typing import Any

import faiss
import numpy as np
from dotenv import load_dotenv
from flask import Flask
from groq import Groq
from sentence_transformers import SentenceTransformer
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardRemove, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

# ────────────────── Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bot")

# ────────────────── Environment
load_dotenv()
BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_ID    = os.getenv("ADMIN_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

DATA_PATH = os.getenv("INDEX_DIR", "/var/data")
TOOLS_JSON_PATH  = "tools.json"
FAISS_INDEX_PATH = os.path.join(DATA_PATH, "tools.faiss")
MAPPING_PATH     = os.path.join(DATA_PATH, "index_to_name.json")

# ────────────────── Globals
TOOLS_DB: list[dict[str, Any]] = []
VECTOR_INDEX: faiss.Index | None = None
INDEX_TO_NAME: dict[int, str] = {}
EMBED_MODEL: SentenceTransformer | None = None

CHOOSE_ACTION, GET_RECOMMENDATION_INPUT = range(2)

# ────────────────── Data loading
def load_all_data() -> None:
    global TOOLS_DB, VECTOR_INDEX, INDEX_TO_NAME, EMBED_MODEL
    try:
        with open(TOOLS_JSON_PATH, "r", encoding="utf-8") as f:
            TOOLS_DB = json.load(f)

        VECTOR_INDEX = faiss.read_index(FAISS_INDEX_PATH)

        with open(MAPPING_PATH, "r", encoding="utf-8") as f:
            INDEX_TO_NAME = {int(k): v for k, v in json.load(f).items()}

        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Resources loaded.")
    except Exception as e:
        logger.critical("FATAL: Could not load resources: %s", e)
        VECTOR_INDEX = None

# ────────────────── Search helpers
def find_candidates(query: str, k: int = 15) -> list[dict[str, Any]]:
    if VECTOR_INDEX is None or EMBED_MODEL is None:
        return []
    emb = EMBED_MODEL.encode([query]).astype("float32")
    _, idxs = VECTOR_INDEX.search(emb, k)
    names = {INDEX_TO_NAME.get(i) for i in idxs[0] if i in INDEX_TO_NAME}
    return [t for t in TOOLS_DB if t.get("name") in names]

def rerank(candidates: list[dict[str, Any]], query: str) -> list[str]:
    if not candidates or not GROQ_API_KEY:
        return []
    client = Groq(api_key=GROQ_API_KEY)
    sys_msg = ("You are a smart recommendation engine. "
               "Return JSON {\"best_matches\": [\"Tool1\", \"Tool2\"]}.")
    usr_msg = (f"User request: \"{query}\"\n\nCandidates:\n"
               f"{json.dumps(candidates, ensure_ascii=False)}")
    resp = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "system", "content": sys_msg},
                  {"role": "user", "content": usr_msg}],
        temperature=0.1,
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content).get("best_matches", [])

def find_tool(name: str) -> dict[str, Any] | None:
    return next((t for t in TOOLS_DB if t.get("name","").lower()==name.lower()), None)

# ────────────────── Bot handlers
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "היי! כתוב לי מה אתה מחפש ואמצא לך כלי מתאים ✨",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GET_RECOMMENDATION_INPUT

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if VECTOR_INDEX is None:
        await update.message.reply_text("המאגר בתחזוקה. נסה מאוחר יותר.")
        return ConversationHandler.END

    query = update.message.text
    await update.message.reply_text("⏳ מחפש…")

    cands = find_candidates(query)
    best  = rerank(cands, query)

    if best:
        for n in best:
            tool = find_tool(n)
            if tool:
                kb = [[InlineKeyboardButton("💰 בדוק מחיר", callback_data=f"price:{tool['name']}")]]
                txt = (f"*{tool['name']}*\n{tool.get('description','')}\n"
                       f"[🔗 קישור]({tool.get('url','#')})")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=txt,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
    else:
        await update.message.reply_text("לא מצאתי התאמה טובה 🙁")

    return GET_RECOMMENDATION_INPUT

async def stats_command(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text(f"Loaded tools: {len(TOOLS_DB)}")

async def price_callback(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Price check coming soon…")

# ────────────────── Keep-alive Flask
flask_app = Flask(__name__)
@flask_app.route("/")
def health():
    return "OK"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# ────────────────── Main
def main() -> None:
    load_all_data()
    if not BOT_TOKEN:
        logger.critical("No BOT_TOKEN env var.")
        return

    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={GET_RECOMMENDATION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recommendation)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(price_callback, pattern=r"^price:"))

    logger.info("Polling…")
    app.run_polling()

if __name__ == "__main__":
    main()
