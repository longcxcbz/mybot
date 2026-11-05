import logging
import os
import sqlite3
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# 💡 导入单独的广告配置文件
import config

# 开启日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ==========================================
# 0. 初始化 SQLite 数据库
# ==========================================
DB_FILE = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            short_code TEXT PRIMARY KEY,
            file_list TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_save_resource(short_code, file_list):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO resources (short_code, file_list) VALUES (?, ?)", 
                   (short_code, json.dumps(file_list)))
    conn.commit()
    conn.close()

def db_get_resource(short_code):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_list FROM resources WHERE short_code = ?", (short_code,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def db_get_all_resources():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT short_code, file_list FROM resources ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        results.append({"short_code": row[0], "count": len(json.loads(row[1]))})
    return results

def db_delete_resource(short_code):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM resources WHERE short_code = ?", (short_code,))
    conn.commit()
    conn.close()

UPLOADING_SESSIONS = {}

# ==========================================
# 1. 维持 Render 端口的网页服务器
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. 接收文件（包含实时更新广告位）
# ==========================================
async def handle_incoming_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    chat_id = message.chat_id

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    else:
        return

    if chat_id not in UPLOADING_SESSIONS:
        UPLOADING_SESSIONS[chat_id] = {"files": [], "msg_id": None}

    UPLOADING_SESSIONS[chat_id]["files"].append({"type": file_type, "file_id": file_id})
    total_count = len(UPLOADING_SESSIONS[chat_id]["files"])

    text = (
        f"📦 **正在收集文件中...**\n\n"
        f"当前已累计暂存：**{total_count}** 个文件\n"
        f"💡 发完后点击下方按钮生成链接。\n\n"
        f"{config.AD_TEXT}"
    )

    keyboard = [
        [InlineKeyboardButton("✅ 已接收完，完成打包并生成", callback_data="finish_group")],
        [InlineKeyboardButton(config.AD_BUTTON_TEXT, url=config.AD_BUTTON_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    current_msg_id = UPLOADING_SESSIONS[chat_id]["msg_id"]
    try:
        if current_msg_id is None:
            sent_msg = await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            UPLOADING_SESSIONS[chat_id]["msg_id"] = sent_msg.message_id
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=current_msg_id, text=text, reply_markup=reply_markup, parse_mode="Markdown"
            )
    except Exception:
        sent_msg = await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        UPLOADING_SESSIONS[chat_id]["msg_id"] = sent_msg.message_id

# ==========================================
# 3. 按钮回调（打包生成 / 管理后台）
# ==========================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "finish_group":
        session_data = UPLOADING_SESSIONS.get(chat_id, {"files": [], "msg_id": None})
        session_files = session_data["files"]

        if not session_files:
            await query.message.reply_text("❌ 当前没有待打包的文件。")
            return

        short_code = session_files[0]["file_id"][-8:]
        db_save_resource(short_code, session_files)
        UPLOADING_SESSIONS[chat_id] = {"files": [], "msg_id": None}

        raw_link = f"https://t.me/{config.BOT_USERNAME}?start={short_code}"

        text = (
            f"🎉 **打包成功并已永久保存！**\n\n"
            f"📁 包含文件总数：{len(session_files)} 个\n"
            f"🔗 **合并分享链接**：\n"
            f"[点击此链接获取全部文件]({raw_link})\n\n"
            f"{config.AD_TEXT}\n\n"
            f"💡 发送 /glwj 可以随时管理历史文件。\n"
            f"复制纯链接：\n`{raw_link}`"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔗 点击获取全部文件", url=raw_link)],
            [InlineKeyboardButton(config.AD_BUTTON_TEXT, url=config.AD_BUTTON_URL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if config.AD_PHOTO:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=config.AD_PHOTO,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    elif data.startswith("del_"):
        short_code = data.split("_")[1]
        db_delete_resource(short_code)
        await query.message.edit_text(f"🗑️ 已成功删除代码为 `{short_code}` 的资源记录。", parse_mode="Markdown")

    elif data.startswith("view_"):
        short_code = data.split("_")[1]
        raw_link = f"https://t.me/{config.BOT_USERNAME}?start={short_code}"
        await query.message.reply_text(
            f"📌 **资源详情**\n识别码：`{short_code}`\n链接：\n`{raw_link}`",
            parse_mode="Markdown"
        )

# ==========================================
# 4. 资源管理后台：/glwj 命令
# ==========================================
async def glwj_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resources = db_get_all_resources()

    if not resources:
        await update.message.reply_text("📂 目前数据库中还没有保存任何资源文件。")
        return

    text = f"🛠️ **资源管理后台**\n共找到 {len(resources)} 组历史保存的文件：\n\n"
    keyboard = []

    for item in resources:
        code = item["short_code"]
        count = item["count"]
        keyboard.append([
            InlineKeyboardButton(f"📦 资源 {code} ({count}个文件)", callback_data=f"view_{code}"),
            InlineKeyboardButton("❌ 删除", callback_data=f"del_{code}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# ==========================================
# 5. 用户通过 /start 触发下发
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    chat_id = update.effective_chat.id

    if args:
        short_code = args[0]
        file_list = db_get_resource(short_code)

        if file_list:
            total = len(file_list)
            await update.message.reply_text(f"🔍 正在为您提取共 {total} 个文件，正在分批发送中...")

            for i in range(0, total, 10):
                chunk = file_list[i:i+10]
                media_group = []
                for item in chunk:
                    if item["type"] == "photo":
                        media_group.append(InputMediaPhoto(media=item["file_id"]))
                    elif item["type"] == "video":
                        media_group.append(InputMediaVideo(media=item["file_id"]))

                try:
                    await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                except Exception as e:
                    await update.message.reply_text(f"❌ 发送分批文件出错: {e}")
        else:
            await update.message.reply_text("❌ 未找到该组文件的记录，链接可能已失效。")
    else:
        await update.message.reply_text("欢迎使用资源打包分发机器人！通过专属链接可获取完整相册。")

# ==========================================
# 6. 主程序入口
# ==========================================
def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("错误: 未找到 TOKEN 环境变量！")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("glwj", glwj_command))  # 💡 已将命令改为 /glwj
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_incoming_media))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("网盘分发机器人正在运行...")
    application.run_polling()

if __name__ == "__main__":
    main()
