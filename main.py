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

# 内存数据库：分享码 -> 文件列表
GROUP_DATABASE = {}

# 临时会话：记录当前正在上传的文件与提示消息的 ID（实现防刷屏动态更新）
# 结构：{ chat_id: {"files": [...], "msg_id": 12345} }
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
# 2. 接收文件：单条消息动态更新，绝不刷屏
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

    # 初始化会话
    if chat_id not in UPLOADING_SESSIONS:
        UPLOADING_SESSIONS[chat_id] = {"files": [], "msg_id": None}

    # 存入文件
    UPLOADING_SESSIONS[chat_id]["files"].append({"type": file_type, "file_id": file_id})
    total_count = len(UPLOADING_SESSIONS[chat_id]["files"])

    # 准备按钮与提示文案
    keyboard = [[InlineKeyboardButton("✅ 已接收完，完成打包并生成", callback_data="finish_group")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"📦 **正在收集文件中...**\n\n"
        f"当前已累计暂存：**{total_count}** 个文件\n"
        f"💡 你可以继续发送（支持几十个视频/图片），发完后点击下方按钮。"
    )

    current_msg_id = UPLOADING_SESSIONS[chat_id]["msg_id"]

    try:
        if current_msg_id is None:
            # 第一次发文件，发送新提示消息
            sent_msg = await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            UPLOADING_SESSIONS[chat_id]["msg_id"] = sent_msg.message_id
        else:
            # 之后不发新消息，直接编辑修改原消息的数字（实现无打扰更新）
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=current_msg_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except Exception:
        # 如果用户把提示消息删了，则重新发一条
        sent_msg = await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        UPLOADING_SESSIONS[chat_id]["msg_id"] = sent_msg.message_id

# ==========================================
# 3. 点击完成打包按钮
# ==========================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    if query.data == "finish_group":
        session_data = UPLOADING_SESSIONS.get(chat_id, {"files": [], "msg_id": None})
        session_files = session_data["files"]

        if not session_files:
            await query.message.reply_text("❌ 当前没有待打包的文件。")
            return

        # 生成短码并保存
        short_code = session_files[0]["file_id"][-8:]
        GROUP_DATABASE[short_code] = session_files

        # 清空当前会话
        UPLOADING_SESSIONS[chat_id] = {"files": [], "msg_id": None}

        bot_username = "Yinheximanyoua_bot"
        raw_link = f"https://t.me/{bot_username}?start={short_code}"

        text = (
            f"🎉 **打包成功！**\n\n"
            f"📁 包含文件总数：{len(session_files)} 个\n"
            f"🔗 **合并分享链接**：\n"
            f"[点击此链接获取全部文件]({raw_link})\n\n"
            f"💡 超过10个文件时，系统会自动分批（每组10个）连续发给用户，完美避免报错。\n"
            f"复制纯链接：\n`{raw_link}`"
        )
        await query.message.reply_text(text, parse_mode="Markdown")

# ==========================================
# 4. 用户通过 /start 触发，自动分批（翻页式）下发
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    chat_id = update.effective_chat.id

    if args:
        short_code = args[0]
        file_list = GROUP_DATABASE.get(short_code)

        if file_list:
            total = len(file_list)
            await update.message.reply_text(f"🔍 正在为您提取共 {total} 个文件，正在分批发送中...")

            # 【核心解决10个限制】：自动按每 10 个一组切片分批发送
            for i in range(0, total, 10):
                chunk = file_list[i:i+10]
                media_group = []
                for item in chunk:
                    if item["type"] == "photo":
                        media_group.append(InputMediaPhoto(media=item["file_id"]))
                    elif item["type"] == "video":
                        media_group.append(InputMediaVideo(media=item["file_id"]))

                try:
                    # 分组连续下发相册
                    await context.bot.send_media_group(chat_id=chat_id, media=media_group)
                except Exception as e:
                    await update.message.reply_text(f"❌ 发送分批文件出错: {e}")
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
