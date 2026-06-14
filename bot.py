"""
Telegram-бот: отправь ссылку Instagram → получи описание от Claude
"""
import os
import re
import logging
import requests
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic
import base64

# Настройки берутся из переменных окружения Railway
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))  # ваш Telegram ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

INSTAGRAM_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w-]+"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие."""
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"Привет! Я анализирую посты Instagram.\n\n"
        f"Просто отправь мне ссылку на пост.\n\n"
        f"Твой Telegram ID: {user_id}"
    )


def get_instagram_image(url: str) -> bytes | None:
    """Скачивает первую картинку с поста Instagram."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148"
            )
        }
        # Instagram отдаёт картинку в og:image мета-теге
        response = requests.get(url, headers=headers, timeout=15)
        match = re.search(r'<meta property="og:image" content="([^"]+)"', response.text)
        if not match:
            return None

        img_url = match.group(1).replace("&amp;", "&")
        img_response = requests.get(img_url, headers=headers, timeout=15)
        return img_response.content
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения со ссылкой Instagram."""
    # Проверка владельца (если задан ALLOWED_USER_ID)
    if ALLOWED_USER_ID and update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("Доступ запрещён.")
        return

    text = update.message.text or ""
    match = INSTAGRAM_URL_PATTERN.search(text)

    if not match:
        await update.message.reply_text(
            "Пришли ссылку на пост Instagram (https://instagram.com/p/...)"
        )
        return

    url = match.group(0)
    await update.message.reply_text("⏳ Скачиваю и анализирую...")

    image_data = get_instagram_image(url)
    if not image_data:
        await update.message.reply_text(
            "❌ Не удалось скачать картинку. Возможно пост приватный "
            "или Instagram заблокировал запрос."
        )
        return

    try:
        base64_image = base64.standard_b64encode(image_data).decode()
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Подробно опиши это изображение из Instagram. "
                                "Если это интерьер — опиши стиль, материалы, мебель, "
                                "цветовую палитру, освещение, особенности. "
                                "Если это что-то другое — опиши, что видишь."
                            ),
                        },
                    ],
                }
            ],
        )
        description = response.content[0].text
        await update.message.reply_text(description)
    except Exception as e:
        logger.error(f"Ошибка Claude: {e}")
        await update.message.reply_text(f"❌ Ошибка анализа: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
