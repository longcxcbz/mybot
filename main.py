import logging
import os
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

# 内存数据库：
# GROUP_DATABASE 存储 分享码 -> 文件列表 (包含 file_id 和 类型)
GROUP_DATABASE = {}

# 临时缓存：记录管理员当前正在上传的未打包文件列表 (chat_id -> [{'type': 'photo/video', 'file_id': 'xxx'}])
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
# 2. 接收文件并暂存，同时提供“完成打包”按钮
# ==========================================
async def handle_incoming_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    chat_id = message.chat_id

    # 提取图片或视频
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    else:
        return

    # 初始化当前用户的上传会话
    if chat_id not in UPLOADING_SESSIONS:
        UPLOADING_SESSIONS[chat_id] = []

    # 将文件加入暂存筐
    UPLOADING_SESSIONS[chat_id].append({"type": file_type, "file_id": file_id})
    count = len(UPLOADING_SESSIONS[chat_id])

    # 附带一个“完成打包并生成链接”的按钮
    keyboard = [[InlineKeyboardButton("✅ 完成打包并生成链接", callback_data="finish_group")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        f"📦 **已成功接收第 {count} 个文件**\n"
        f"💡 你可以继续发送图片或视频，或者点击下方按钮生成一个包含所有文件的合并链接。",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ==========================================
# 3. 点击按钮后，生成多文件合一的分享链接
# ==========================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "finish_group":
        session_files = UPLOADING_SESSIONS.get(chat_id, [])
        if not session_files:
            await query.message.reply_text("❌ 当前没有待打包的文件，请先发送图片或视频。")
            return

        # 生成一个短码（取第一个文件 file_id 的前 8 位）
        short_code = session_files[0]["file_id"][-8:]
        # 保存这组文件
        GROUP_DATABASE[short_code] = session_files

        # 清空当前会话
        UPLOADING_SESSIONS[chat_id] = []

        bot_username = "Yinheximanyoua_bot"
        raw_link = f"https://t.me/{bot_username}?start={short_code}"

        text = (
            f"🎉 **多文件打包成功！**\n\n"
            f"📁 包含文件总数：{len(session_files)} 个\n"
            f"🔗 **合并分享链接**：\n"
            f"[点击此链接获取全部文件]({raw_link})\n\n"
            f"💡 别人点击此链接，将一次性收到这组图文/视频相册。\n"
            f"复制纯链接：\n`{raw_link}`"
        )
        await query.message.reply_text(text, parse_mode="Markdown")

# ==========================================
# 4. 用户通过 /start 触发，合并下发相册
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    chat_id = update.effective_chat.id

    if args:
        short_code = args[0]
        file_list = GROUP_DATABASE.get(short_code)

        if file_list:
            await update.message.reply_text("🔍 正在为您打包提取全部文件，请稍候...")
            
            # 构造 Telegram 的 MediaGroup 媒体组格式
            media_group = []
            for item in file_list:
                if item["type"] == "photo":
                    media_group.append(InputMediaPhoto(media=item["file_id"]))
                elif item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["file_id"]))

            try:
                # 一次性整齐地合并发送多张图片或视频
                await context.bot.send_media_group(chat_id=chat_id, media=media_group)
            except Exception as e:
                await update.message.reply_text(f"❌ 发送文件组失败: {e}")
        else:
            await update.message.reply_text("❌ 未找到该组文件的记录，链接可能已失效。")
    else:
        await update.message.reply_text("欢迎使用资源打包分发机器人！通过专属链接可获取完整相册。")

# ==========================================
# 5. 主程序入口
# ==========================================
def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("错误: 未找到 TOKEN 环境变量！")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_incoming_media))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("网盘分发机器人正在运行...")
    application.run_polling()

if __name__ == "__main__":
    main()
