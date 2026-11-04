import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import os

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ad_text = (
        "✨ **求档/资源处理成功**\n\n"
        "🔥 **赞助商广告：**\n"
        "点击下方按钮访问我们的高速专线/机场👇"
    )
    keyboard = [[InlineKeyboardButton("👉 点击进入专属通道", url="https://nsnnmz.xn--66tw07h.com")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(ad_text, parse_mode="Markdown", reply_markup=reply_markup)

def main():
    TOKEN = os.environ.get("TOKEN")
    
    if not TOKEN:
        print("错误：未找到 TOKEN 环境变量！")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))

    print("机器人正在云端稳定运行...")
    app.run_polling()

if __name__ == '__main__':
    main()
