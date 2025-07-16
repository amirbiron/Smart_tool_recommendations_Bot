import os
import logging
import json
import threading
from dotenv import load_dotenv

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
CHOOSE_ACTION, GET_RECOMMENDATION_INPUT, GET_KEYWORD_SEARCH_INPUT, WEB_SEARCH_PROMPT = range(4)

def load_tools():
    try:
        with open('tools.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading tools.json: {e}")
        return []

tools_db = load_tools()
tools_db_string = json.dumps(tools_db, ensure_ascii=False)

def get_semantic_recommendation(user_text: str) -> list:
    logger.info("Performing semantic search...")
    try:
        if not GROQ_API_KEY: return []
        client = Groq(api_key=GROQ_API_KEY)
        system_prompt = (
            "You are a smart assistant. Your task is to analyze the user's request and find the best matching tools from a provided JSON list. "
            "Return a JSON object with a single key, 'best_matches', containing a list of the names of the top 1-3 most relevant tools. "
            "Example response: {\"best_matches\": [\"ToolName1\", \"ToolName2\"]}. "
            "If no tools are relevant, return an empty list."
        )
        user_prompt = (
            f"User's request: \"{user_text}\"\n\n"
            f"Here is the list of available tools in JSON format:\n{tools_db_string}"
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
        logger.info(f"Semantic search response from Groq: {response_content}")
        data = json.loads(response_content)
        return data.get("best_matches", [])
    except Exception as e:
        logger.error(f"Error in get_semantic_recommendation: {e}")
        return []

def get_web_recommendation_from_groq(user_text: str) -> str:
    logger.info(f"Performing web search for: {user_text}")
    try:
        if not GROQ_API_KEY: return "לא ניתן היה לבצע חיפוש ברשת."
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful tech expert who communicates in Hebrew. The user is looking for a tool. Based on their request, recommend 1-2 tools from your knowledge base. For each tool, provide its name and a short description in Hebrew. Format the response cleanly.",
                },
                {"role": "user", "content": user_text},
            ],
            model="llama3-70b-8192",
            temperature=0.4, max_tokens=500,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error in get_web_recommendation_from_groq: {e}")
        return "אירעה שגיאה בעת החיפוש ברשת."

def get_price_from_groq(tool_name: str) -> str:
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
    query = update.callback_query
    await query.answer()
    tool_name = query.data.split(':', 1)[1]
    original_data = context.user_data.get(f"tool_{tool_name}")
    if original_data:
        await query.edit_message_text(text=original_data["text"], reply_markup=original_data["markup"], parse_mode='Markdown')
    else:
        await query.edit_message_text(text="אירעה שגיאה. לא נמצא המידע המקורי.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    logger.info(f"User {user.first_name} (ID: {user.id}) started the bot.")
    if db is not None:
        try:
            db.users.update_one({'_id': user.id}, {'$setOnInsert': {'first_name': user.first_name, 'username': user.username}}, upsert=True)
        except Exception as e:
            logger.error(f"Failed to save user {user.id} to MongoDB: {e}")
    reply_keyboard = [["🧠 המלצה חכמה"], ["🔍 חיפוש מהיר"]]
    await update.message.reply_text("👋 שלום!\nאני בוט המלצות חכם. תאר לי מה אתה צריך ואמצא לך את הכלי המתאים ביותר.", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_choice = update.message.text
    if user_choice == "🧠 המלצה חכמה":
        await update.message.reply_text("מעולה! תאר לי במילים שלך, כמה שיותר בפירוט, איזה כלי אתה מחפש...", reply_markup=ReplyKeyboardRemove())
        return GET_RECOMMENDATION_INPUT
    elif user_choice == "🔍 חיפוש מהיר":
        await update.message.reply_text("בטח, הקלד מילת מפתח אחת לחיפוש מהיר...", reply_markup=ReplyKeyboardRemove())
        return GET_KEYWORD_SEARCH_INPUT
    return CHOOSE_ACTION

async def get_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("--- Entering get_recommendation (v19) ---")
    user_text = update.message.text
    context.user_data['last_query'] = user_text
    await update.message.reply_text("קיבלתי. מנתח את הבקשה שלך מול המאגר שלי... 🤖")
    
    recommended_tool_names = get_semantic_recommendation(user_text)
    
    if recommended_tool_names:
        logger.info(f"Found {len(recommended_tool_names)} local recommendations.")
        await update.message.reply_text("✨ אלו הכלים שמצאתי שהכי מתאימים לבקשה שלך:")
        for tool_name in recommended_tool_names:
            tool = find_tool_by_name(tool_name)
            if tool:
                await send_tool_recommendation(update, context, tool)
    else:
        logger.info("No local recommendations found.")
        await update.message.reply_text("לא מצאתי התאמה טובה במאגר שלי.")

    logger.info("Now, offering web search option.")
    reply_keyboard = [["🌐 חפש ברשת"], ["🏠 חזרה לתפריט הראשי"]]
    await update.message.reply_text(
        "תרצה שאבצע חיפוש רחב יותר ברשת?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    
    return WEB_SEARCH_PROMPT

async def web_search_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    choice = update.message.text
    if choice == "🌐 חפש ברשת":
        last_query = context.user_data.get('last_query', '')
        if not last_query:
            await update.message.reply_text("אירעה שגיאה, לא זוכר מה חיפשנו. נחזור לתפריט הראשי.", reply_markup=ReplyKeyboardRemove())
            return await start(update, context)

        await update.message.reply_text(f"בסדר, מבצע חיפוש רחב יותר ברשת עבור '{last_query}'...", reply_markup=ReplyKeyboardRemove())
        web_results = get_web_recommendation_from_groq(last_query)
        await update.message.reply_text(web_results)
        
    return await start(update, context)

async def keyword_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyword = update.message.text
    context.user_data['last_query'] = keyword
    await update.message.reply_text(f"מחפש כלים עם המילה '{keyword}' במאגר שלי...")
    matched_tools = find_tools_in_db([keyword])
    if not matched_tools:
        await update.message.reply_text("לא מצאתי כלים התואמים למילת המפתח הזו במאגר שלי.")
    else:
        await update.message.reply_text(f"🔍 תוצאות חיפוש עבור '{keyword}':")
        for tool in matched_tools:
            await send_tool_recommendation(update, context, tool)

    reply_keyboard = [["🌐 חפש ברשת"], ["🏠 חזרה לתפריט הראשי"]]
    await update.message.reply_text(
        "תרצה שאבצע חיפוש רחב יותר ברשת?",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    return WEB_SEARCH_PROMPT

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
            WEB_SEARCH_PROMPT: [
                MessageHandler(filters.Regex("^🌐 חפש ברשת$"), web_search_prompt_handler),
                MessageHandler(filters.Regex("^🏠 חזרה לתפריט הראשי$"), start),
            ]
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
