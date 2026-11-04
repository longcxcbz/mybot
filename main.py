import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# 开启日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# 1. 维持 Render Web Service 必需的极简端口服务器
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

# 2. 核心功能：处理带参数的 /start 命令
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        file_key = args[0]  # 获取链接里的参数（例如 file_id 或资源编号）
        await update.message.reply_text(f"正在为您提取资源，编号：{file_key}")
        # 这里你可以直接通过 file_key（文件ID）把图片或视频发给用户：
        # await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_key)
    else:
        await update.message.reply_text("欢迎使用！请通过专属推广链接进入本机器人。")

def main():
    token = os.environ.get("TOKEN")
    if not token:
        print("错误: 未找到 TOKEN 环境变量！")
        return

    application = ApplicationBuilder().token(token).build()
    
    # 注册 /start 命令监听
    application.add_handler(CommandHandler("start", start))

    print("机器人已启动...")
    application.run_polling()

if __name__ == "__main__":
    main()
