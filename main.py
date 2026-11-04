from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)


# 处理带参数的 /start 命令
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
  # 获取用户传过来的参数（例如 start=video_123 中的 video_123）
  args = context.args

  if args:
    file_key = args[0]
    # 这里你可以根据 file_key 去数据库或字典里查找对应的文件 ID
    # 假设我们直接把 file_key 当作之前保存的 file_id 发送给用户
    await update.message.reply_text(
        f"正在为您提取资源，编号：{file_key}"
    )

    # 示例：直接把文件发送给用户
    # await context.bot.send_video(chat_id=update.effective_chat.id, video=file_key)
  else:
    await update.message.reply_text(
        "欢迎使用本机器人！请点击正确的专属通道链接获取资源。"
    )


def main():
  token = "9121200118:AAGvpRtLR-YVPaXhMNac6NOZ4z_E1Gbf2zI"
  application = ApplicationBuilder().token(token).build()

  # 注册 /start 命令处理器
  application.add_handler(CommandHandler("start", start))

  print("机器人正在运行...")
  application.run_polling()


if __name__ == "__main__":
  main()
