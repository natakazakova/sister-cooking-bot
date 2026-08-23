import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from recipe import back_to_category, recipes, show_category, show_recipe
from blog import blog

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для sister.cooking 🍳\n\n"
        "/recipes — рецепты"
        "\n/blog — публикации в блоге"
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("recipes", recipes))
    app.add_handler(CommandHandler("blog", blog))
    app.add_handler(CommandHandler("back", back_to_category))
    app.add_handler(
        CallbackQueryHandler(
            show_category,
            pattern=r"^category:",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            show_recipe,
            pattern=r"^recipe:",
        )
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
