import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
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

# 内存临时字典（用来存储 文件短码 -> file_id 的对应关系）
FILE_DATABASE = {}

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
# 2. 核心功能 A：接收你发的文件，生成分享链接
# ==========================================
async def handle_incoming_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # 提取图片或视频的 file_id
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "图片"
    elif message.video:
        file_id = message.video.file_id
        file_type = "视频"
    else:
        return

    # 生成一个简短的唯一编号（取 file_id 的前 8 位）
    short_code = file_id[-8:]
    FILE_DATABASE[short_code] = file_id

    # 直接使用你当前的真实机器人用户名
    bot_username = "Yinheximanyoua_bot"
    raw_link = f"https://t.me/{bot_username}?start={short_code}"

    # 使用 Markdown 超链接语法
    text = (
        f"✅ **已接收并保存登记**\n\n"
        f"📦 类型：{file_type}\n"
        f"🔗 **专属分享链接**：\n"
        f"[点击此链接直接获取文件]({raw_link})\n\n"
        f"💡 如果无法直接点击，请复制下方完整链接：\n`{raw_link}`"
    )

    await message.reply_text(text, parse_mode="Markdown")

# ==========================================
# 3. 核心功能 B：用户点击链接触发 /start，下发文件
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    chat_id = update.effective_chat.id

    if args:
        short_code = args[0]
        # 在数据库中查找对应的 file_id
        file_id = FILE_DATABASE.get(short_code)

        if file_id:
            await update.message.reply_text("🔍 正在为您提取文件，请稍候...")
            # 自动把对应的图片或视频发给用户
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=file_id)
            except Exception:
                try:
                    await context.bot.send_video(chat_id=chat_id, video=file_id)
                except Exception:
                    await update.message.reply_text("❌ 文件提取失败或已失效。")
        else:
            await update.message.reply_text("❌ 未找到该文件的记录，链接可能已失效（如服务重启过）。")
    else:
        await update.message.reply_text("欢迎使用资源分发机器人！请通过专属链接获取内容。")

# ==========================================
# 4. 主程序入口
# ==========================================
def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("错误: 未找到 TOKEN 环境变量！")
        return

    application = ApplicationBuilder().token(token).build()

    # 注册 /start 命令
    application.add_handler(CommandHandler("start", start_command))
    # 注册接收媒体文件的处理器
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_incoming_media))

    print("网盘分发机器人正在运行...")
    application.run_polling()

if __name__ == "__main__":
    main()
