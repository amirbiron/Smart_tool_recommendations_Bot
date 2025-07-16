#!/usr/bin/env python3
# main.py — Telegram AI-tools bot (original flow)

import json, logging, os, threading
from typing import Any

import faiss, numpy as np
from dotenv import load_dotenv
from flask import Flask
from groq import Groq
from sentence_transformers import SentenceTransformer
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardRemove, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, ConversationHandler, MessageHandler,
                          filters)

# ── Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
logger = logging.getLogger("bot")

# ── Environment
load_dotenv()
BOT_TOKEN    = os.getenv("BOT_TOKEN")
ADMIN_ID     = os.getenv("ADMIN_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

DATA_PATH = os.getenv("INDEX_DIR", "/var/data")
TOOLS_JSON_PATH  = "tools.json"
FAISS_INDEX_PATH = os.path.join(DATA_PATH, "tools.faiss")
MAPPING_PATH     = os.path.join(DATA_PATH, "index_to_name.json")

# ── Globals
TOOLS_DB: list[dict[str, Any]] = []
VECTOR_INDEX: faiss.Index | None = None
INDEX_TO_NAME: dict[int, str] = {}
EMBED_MODEL: SentenceTransformer | None = None

CHOOSE_ACTION, GET_RECOMMEND_INPUT = range(2)

# ── Load resources
def load_all_data() -> None:
    global TOOLS_DB, VECTOR_INDEX, INDEX_TO_NAME, EMBED_MODEL
    try:
        with open(TOOLS_JSON_PATH, encoding="utf-8") as f:
            TOOLS_DB = json.load(f)
        VECTOR_INDEX = faiss.read_index(FAISS_INDEX_PATH)
        with open(MAPPING_PATH, encoding="utf-8") as f:
            INDEX_TO_NAME = {int(k): v for k, v in json.load(f).items()}
        EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Resources loaded ✅")
    except Exception as exc:
        logger.critical("FATAL: Could not load resources: %s", exc)
        VECTOR_INDEX = None

# ── Search helpers
def vector_search(q: str, k: int = 15):
    if VECTOR_INDEX is None or EMBED_MODEL is None:
        return []
    emb = EMBED_MODEL.encode([q]).astype("float32")
    _, idxs = VECTOR_INDEX.search(emb, k)
    names = {INDEX_TO_NAME.get(i) for i in idxs[0] if i in INDEX_TO_NAME}
    return [t for t in TOOLS_DB if t.get("name") in names]

def rerank(cands, q: str):
    if not cands or not GROQ_API_KEY:
        return []
    client = Groq(api_key=GROQ_API_KEY)
    sys = "Return JSON {\"best_matches\":[...]}"
    usr = f"User: {q}\nCandidates:\n{json.dumps(cands, ensure_ascii=False)}"
    resp = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role":"system","content":sys},
                  {"role":"user","content":usr}],
        temperature=0.1, max_tokens=200,
        response_format={"type":"json_object"},
    )
    return json.loads(resp.choices[0].message.content).get("best_matches", [])

def find_tool(name: str):
    return next((t for t in TOOLS_DB if t["name"].lower()==name.lower()), None)

# ── Handlers
async def start(update: Update, _):
    await update.message.reply_text(
        "היי! כתוב לי מה אתה מחפש, ואמצא לך את הכלי הכי מתאים 🤖",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GET_RECOMMEND_INPUT

async def choose_action(update: Update, _):
    return GET_RECOMMEND_INPUT  # אין מקלדת תפריט, ממשיכים לחיפוש

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if VECTOR_INDEX is None:
        await update.message.reply_text("המאגר בתחזוקה. נסה מאוחר יותר.")
        return ConversationHandler.END

    q = update.message.text
    await update.message.reply_text("⏳ מחפש…")
    best = rerank(vector_search(q), q)

    if best:
        await update.message.reply_text("✨ הכלים המתאימים ביותר:")
        for n in best:
            t = find_tool(n)
            if t:
                kb = [
                    [InlineKeyboardButton("💰 בדוק מחיר עדכני",
                                          callback_data=f"price_check:{t['name']}")],
                    [InlineKeyboardButton("⬅️ חזור",
                                          callback_data=f"back_to_tool:{t['name']}")]
                ]
                txt = f"🧠 *{t['name']}*\n{t.get('description','')}\n[🔗 קישור]({t.get('url','#')})"
                await context.bot.send_message(
                    update.effective_chat.id, txt,
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                )
    else:
        await update.message.reply_text("לא מצאתי התאמה 🙁")
    return GET_RECOMMEND_INPUT

async def price_check_callback(update: Update, _):
    await update.callback_query.answer("Price check coming soon…")

async def back_to_tool_callback(update: Update, _):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "מוכן לבקשה חדשה – או /start כדי להתחיל מחדש."
    )

async def stats_command(update: Update, _):
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text(f"Loaded tools: {len(TOOLS_DB)}")

# ── Keep-alive
flask_app = Flask(__name__)
@flask_app.route("/")
def ping(): return "OK"

def run_flask(): flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

# ── Main
def main():
    load_all_data()
    if not BOT_TOKEN:
        logger.critical("Missing BOT_TOKEN"); return
    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            GET_RECOMMEND_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recommendation)],
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
