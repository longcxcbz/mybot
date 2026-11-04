import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

# 开启日志记录
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ==========================================
# 1. 网页服务器（用来应付 Render 的端口检测，避免超时报错）
# ==========================================


class SimpleHandler(BaseHTTPRequestHandler):

  def do_GET(self):
    self.send_response(200)
    self.end_headers()
    self.wfile.write(b"Bot is alive and running!")

  def log_message(self, format, *args):
    # 屏蔽常规请求日志，保持控制台干净
    return


def run_web_server():
  port = int(os.environ.get("PORT", 10000))
  server = HTTPServer(("0.0.0.0", port), SimpleHandler)
  server.serve_forever()


# 在后台线程启动网页服务器
threading.Thread(target=run_web_server, daemon=True).start()


# ==========================================
# 2. Telegram 机器人核心业务逻辑
# ==========================================
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
  # 检查消息中是否有图片或视频
  if update.message.photo:
    file_id = update.message.photo[-1].file_id
  elif update.message.video:
    file_id = update.message.video.file_id
  else:
    return

  # 获取文件的 Telegram 云端直链
  file = await context.bot.get_file(file_id)
  file_url = file.file_path

  # 设置广告按钮（你可以随时修改这里的文字和链接）
  keyboard = [[
      InlineKeyboardButton(
          "👉 点击进入专属广告通道", url="https://t.me/你的频道链接"
      )
  ]]
  reply_markup = InlineKeyboardMarkup(keyboard)

  # 回复用户带直链和广告按钮的信息
  await update.message.reply_text(
      f"文件处理成功！\n直链地址：\n{file_url}\n\n感谢使用本服务！",
      reply_markup=reply_markup,
  )


# ==========================================
# 3. 主程序入口
# ==========================================
def main():
  # 从 Render 环境变量中读取 TOKEN
  token = os.environ.get("TOKEN")
  if not token:
    print("错误: 未找到 TOKEN 环境变量！")
    return

  # 构建机器人应用
  application = ApplicationBuilder().token(token).build()

  # 注册监听图片和视频的消息处理器
  application.add_handler(
      MessageHandler(filters.PHOTO | filters.VIDEO, handle_media)
  )

  print("机器人正在云端稳定运行...")
  # 启动长轮询接收消息
  application.run_polling()


if __name__ == "__main__":
  main()
