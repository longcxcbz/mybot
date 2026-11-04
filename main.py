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

# 开启日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ==========================================
# 🎁 广告配置区域（以后只需在这里修改文案和链接即可）
# ==========================================
AD_TEXT = (
    "━━━━━━━━━━━━\n"
    "📢 **赞助商 / 长期福利频道**：\n"
    "👉 点击加入 [@你的主频道名称](https://t.me/你的频道链接)\n"
    "苹果限免 App 每日分享，精品资源不迷路！"
)
AD_BUTTON_TEXT = "📢 关注苹果限免/优质广告频道"
AD_BUTTON_URL = "https://t.me/你的频道链接"
# ==========================================

# ==========================================
# 0. 初始化 SQLite 数据库（实现永久保存，重启不丢）
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

# 临时会话缓存
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
# 2. 接收文件：防刷屏动态更新
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

    keyboard = [[InlineKeyboardButton("✅ 已接收完，完成打包并生成", callback_data="finish_group")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"📦 **正在收集文件中...**\n\n"
        f"当前已累计暂存：**{total_count}** 个文件\n"
        f"💡 发完
