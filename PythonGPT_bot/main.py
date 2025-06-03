from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import openai
import os
from dotenv import load_dotenv
from util import (
    send_photo, send_text, load_message, show_main_menu
)
from gpt_service.gpt import gpt, gpt_dialog
from osnov_servis.random_facts import get_random_fact
from osnov_servis.talk import talk, talk_dialog, load_character_prompt
from osnov_servis.shared import dialog, chatgpt
from osnov_servis.quiz import (
    quiz_command, quiz_start, topic_selected,
    handle_quiz_answer, handle_quiz_callback,
    SELECTING_TOPIC, ANSWERING_QUESTION
)
from osnov_servis.business_ideas import (
    business_command, business_start, category_selected,
    handle_business_callback, SELECTING_CATEGORY, GENERATING_IDEA
)

import httpx
import logging

from telegram import InputMediaPhoto

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Проверяем наличие необходимых переменных окружения
required_env_vars = ["TG_BOT_TOKEN", "CHATGPT_TOKEN"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Отсутствуют необходимые переменные окружения: {', '.join(missing_vars)}")

# Инициализируем приложение Telegram
try:
    application = Application.builder().token(os.getenv("TG_BOT_TOKEN")).build()
except Exception as e:
    raise RuntimeError(f"Ошибка при инициализации Telegram бота: {e}")

# Состояния для GPT диалога
CHATTING = 0


async def start(update, context):
    """Обработчик команды /start"""
    dialog.mode = "main"
    text = load_message("main")
    await send_photo(update, context, "main")
    await send_text(update, context, text)
    await show_main_menu(update, context, {
        "start": "главное меню бота",
        "gpt": "задать вопрос чату GPT 🧠",
        "talk": "переписка со звездами 😈",
        "fact": "рандомный факт",
        "quiz": "проверь свои знания 🎯",
        "business": "генератор идей для бизнеса 💡"
    })


async def talk_button(update, context):
    """Обработчик кнопки диалога с личностями"""
    query = update.callback_query
    await query.answer()
    await send_photo(update, context, query.data)
    await send_text(update, context, "отличный выбор! Можете начать общаться!")
    prompt = load_character_prompt(query.data)
    chatgpt.set_prompt(prompt)


async def random_fact(update, context):
    """Обработчик команды случайного факта"""
    fact = get_random_fact()

    # Создаем клавиатуру с кнопками
    keyboard = [
        [InlineKeyboardButton("🎲 Еще факт", callback_data="new_fact")],
        [InlineKeyboardButton("📚 Еще факт (без картинки)", callback_data="new_fact_no_photo")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Если это первый вызов (через команду /fact)
    if update.message:
        await send_photo(update, context, "facts")
        await update.message.reply_text(
            f"📚 <b>Интересный факт:</b>\n\n{fact}",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    # Если это повторный вызов (через кнопку)
    else:
        query = update.callback_query
        await query.answer()

        # Получаем новый факт
        new_fact = get_random_fact()

        try:
            # Пытаемся обновить сообщение
            await query.edit_message_text(
                f"📚 <b>Интересный факт:</b>\n\n{new_fact}",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении факта: {e}")
            # Если ошибка, отправляем новое сообщение
            await query.message.reply_text(
                f"📚 <b>Интересный факт:</b>\n\n{new_fact}",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )


async def fact_button(update, context):
    """Обработчик кнопки нового факта"""
    query = update.callback_query
    await query.answer()

    if query.data == "new_fact_no_photo":
        # Получаем новый факт без картинки
        fact = get_random_fact()
        keyboard = [
            [InlineKeyboardButton("🎲 Еще факт", callback_data="new_fact")],

        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                f"📚 <b>Интересный факт:</b>\n\n{fact}",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении факта: {e}")
            await query.message.reply_text(
                f"📚 <b>Интересный факт:</b>\n\n{fact}",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    else:
        return await random_fact(update, context)


async def business_button(update, context):
    """Обработчик кнопки генератора идей"""
    query = update.callback_query
    await query.answer()
    return await business_start(update, context)


# Создаем обработчики для квиза
quiz_handler = ConversationHandler(
    entry_points=[
        CommandHandler('quiz', quiz_command),
        CallbackQueryHandler(quiz_start, pattern='^quiz_interface$')
    ],
    states={
        SELECTING_TOPIC: [
            CallbackQueryHandler(topic_selected, pattern=r'^quiz_topic_'),
            CallbackQueryHandler(handle_quiz_callback, pattern=r'^quiz_')
        ],
        ANSWERING_QUESTION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quiz_answer),
            CallbackQueryHandler(handle_quiz_callback, pattern=r'^quiz_')
        ]
    },
    fallbacks=[
        CommandHandler('quiz', quiz_command),
        CallbackQueryHandler(quiz_start, pattern='^quiz_interface$')
    ],
    per_chat=True,
    per_message=False,
    name="quiz_conversation"
)

# Создаем обработчики для генератора идей
business_handler = ConversationHandler(
    entry_points=[
        CommandHandler('business', business_command),
        CallbackQueryHandler(business_start, pattern='^business_interface$')
    ],
    states={
        SELECTING_CATEGORY: [
            CallbackQueryHandler(category_selected, pattern=r'^business_category_'),
            CallbackQueryHandler(handle_business_callback, pattern=r'^business_'),
            CallbackQueryHandler(handle_business_callback, pattern=r'^main_menu$')
        ],
        GENERATING_IDEA: [
            CallbackQueryHandler(handle_business_callback, pattern=r'^business_'),
            CallbackQueryHandler(handle_business_callback, pattern=r'^main_menu$')
        ]
    },
    fallbacks=[
        CommandHandler('business', business_command),
        CallbackQueryHandler(business_start, pattern='^business_interface$')
    ],
    per_chat=True,
    per_message=False,
    name="business_conversation"
)


async def gpt_command(update, context):
    """Обработчик команды /gpt"""
    await send_photo(update, context, "gpt")
    await send_text(update, context, "🤖 <b>Добро пожаловать в чат с GPT!</b>\n\n"
                                     "Я могу помочь вам с различными темами. "
                                     "Выберите интересующую вас категорию ниже:")

    keyboard = [
        [
            InlineKeyboardButton("💭 Общие вопросы", callback_data="gpt_topic_general"),
            InlineKeyboardButton("💻 Программирование", callback_data="gpt_topic_programming")
        ],
        [
            InlineKeyboardButton("🔬 Наука", callback_data="gpt_topic_science"),
            InlineKeyboardButton("🎨 Искусство", callback_data="gpt_topic_art")
        ],
        [
            InlineKeyboardButton("📚 Образование", callback_data="gpt_topic_education"),
            InlineKeyboardButton("💼 Бизнес", callback_data="gpt_topic_business")
        ],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="gpt_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎯 <b>Выберите тему для общения:</b>\n\n"
        "💡 <i>Каждая тема имеет свои особенности и специализацию</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return CHATTING


async def gpt_start(update, context):
    """Обработчик начала диалога с GPT"""
    query = update.callback_query
    await query.answer()
    await send_photo(update, context, "gpt")
    await send_text(update, context, "🤖 <b>Добро пожаловать в чат с GPT!</b>\n\n"
                                     "Я могу помочь вам с различными темами. "
                                     "Выберите интересующую вас категорию ниже:")

    keyboard = [
        [
            InlineKeyboardButton("💭 Общие вопросы", callback_data="gpt_topic_general"),
            InlineKeyboardButton("💻 Программирование", callback_data="gpt_topic_programming")
        ],
        [
            InlineKeyboardButton("🔬 Наука", callback_data="gpt_topic_science"),
            InlineKeyboardButton("🎨 Искусство", callback_data="gpt_topic_art")
        ],
        [
            InlineKeyboardButton("📚 Образование", callback_data="gpt_topic_education"),
            InlineKeyboardButton("💼 Бизнес", callback_data="gpt_topic_business")
        ],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="gpt_main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "🎯 <b>Выберите тему для общения:</b>\n\n"
        "💡 <i>Каждая тема имеет свои особенности и специализацию</i>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    return CHATTING


async def gpt_topic_selected(update, context):
    """Обработчик выбора темы GPT"""
    query = update.callback_query
    await query.answer()

    topic = query.data.split('_')[-1]
    topics = {
        'general': "💭 общие вопросы",
        'programming': "💻 программирование",
        'science': "🔬 науку",
        'art': "🎨 искусство",
        'education': "📚 образование",
        'business': "💼 бизнес"
    }

    topic_descriptions = {
        'general': "Задавайте любые вопросы на общие темы. Я постараюсь дать вам максимально полезный и информативный ответ.",
        'programming': "Вопросы по программированию, алгоритмам и технологиям. Могу помочь с кодом, объяснить концепции и предложить решения.",
        'science': "Обсуждение научных тем и открытий. От физики до биологии, от химии до астрономии.",
        'art': "Разговоры об искусстве, культуре и творчестве. Обсуждение произведений, стилей и направлений.",
        'education': "Вопросы по обучению и образованию. Помощь в изучении новых предметов и концепций.",
        'business': "Темы бизнеса, предпринимательства и экономики. Анализ идей, стратегий и тенденций."
    }

    try:
        # Создаем клавиатуру с кнопками
        keyboard = [
            [InlineKeyboardButton("❓ Задать вопрос", callback_data="gpt_ask_question")],
            [InlineKeyboardButton("🔄 Сменить тему", callback_data="gpt_change_topic")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="gpt_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            f"✅ <b>Вы выбрали тему: {topics.get(topic, topic)}</b>\n\n"
            f"<i>{topic_descriptions.get(topic, '')}</i>\n\n"
            "💡 Теперь вы можете задавать вопросы. Я постараюсь дать вам подробный и полезный ответ.\n\n"
            "🔙 Для возврата в меню используйте кнопку ниже:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CHATTING
    except Exception as e:
        logger.error(f"Ошибка при выборе темы: {e}")
        await query.message.reply_text(
            "😔 <b>Произошла ошибка при выборе темы</b>\n"
            "Пожалуйста, попробуйте еще раз",
            parse_mode='HTML'
        )
        return CHATTING


async def handle_gpt_message(update, context):
    """Обработчик сообщений для GPT"""
    try:
        # Отправляем индикатор набора текста с анимацией
        status_message = await update.message.reply_text(
            "💭 <i>Думаю над ответом</i>",
            parse_mode='HTML'
        )

        # Получаем ответ от GPT
        response = await gpt(update.message.text)

        # Создаем клавиатуру с кнопками
        keyboard = [
            [InlineKeyboardButton("❓ Задать еще вопрос", callback_data="gpt_ask_question")],
            [InlineKeyboardButton("🔄 Сменить тему", callback_data="gpt_change_topic")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="gpt_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Удаляем сообщение о статусе
        await status_message.delete()

        # Отправляем ответ с красивым форматированием
        await update.message.reply_text(
            f"🤖 <b>Ответ GPT:</b>\n\n{response}\n\n"
            "💡 <i>Вы можете задать новый вопрос, сменить тему или вернуться в меню</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    except Exception as e:
        # В случае ошибки отправляем сообщение об ошибке
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать снова", callback_data="gpt_retry")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="gpt_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "😔 <b>Произошла ошибка при обработке запроса</b>\n\n"
            "Пожалуйста, попробуйте еще раз или вернитесь в меню.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        logger.error(f"Ошибка в handle_gpt_message: {e}")

    return CHATTING


async def handle_gpt_callback(update, context):
    """Обработчик callback-запросов для GPT"""
    query = update.callback_query
    await query.answer()

    if query.data == "gpt_main_menu":
        try:
            # Очищаем историю сообщений GPT
            chatgpt.message_list.clear()

            # Отправляем сообщение о возврате в меню
            await query.message.reply_text(
                "🏠 <b>Возвращаемся в главное меню...</b>",
                parse_mode='HTML'
            )

            # Показываем главное меню
            await show_main_menu(update, context, {
                "start": "главное меню бота",
                "gpt": "задать вопрос чату GPT 🧠",
                "talk": "переписка со звездами 😈",
                "fact": "рандомный факт",
                "quiz": "проверь свои знания 🎯",
                "business": "генератор идей для бизнеса 💡"
            })
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Ошибка при возврате в меню: {e}")
            await query.message.reply_text(
                "😔 <b>Произошла ошибка при возврате в меню</b>\n"
                "Пожалуйста, используйте команду /start",
                parse_mode='HTML'
            )
            return ConversationHandler.END

    elif query.data == "gpt_change_topic":
        try:
            # Отправляем фото и приветственное сообщение
            await send_photo(update, context, "gpt")
            await send_text(update, context, "🤖 <b>Добро пожаловать в чат с GPT!</b>\n\n"
                                             "Я могу помочь вам с различными темами. "
                                             "Выберите интересующую вас категорию ниже:")

            # Создаем клавиатуру с темами
            keyboard = [
                [
                    InlineKeyboardButton("💭 Общие вопросы", callback_data="gpt_topic_general"),
                    InlineKeyboardButton("💻 Программирование", callback_data="gpt_topic_programming")
                ],
                [
                    InlineKeyboardButton("🔬 Наука", callback_data="gpt_topic_science"),
                    InlineKeyboardButton("🎨 Искусство", callback_data="gpt_topic_art")
                ],
                [
                    InlineKeyboardButton("📚 Образование", callback_data="gpt_topic_education"),
                    InlineKeyboardButton("💼 Бизнес", callback_data="gpt_topic_business")
                ],
                [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="gpt_main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем сообщение с темами
            await query.message.reply_text(
                "🎯 <b>Выберите тему для общения:</b>\n\n"
                "💡 <i>Каждая тема имеет свои особенности и специализацию</i>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return CHATTING
        except Exception as e:
            logger.error(f"Ошибка при смене темы: {e}")
            await query.message.reply_text(
                "😔 <b>Произошла ошибка при смене темы</b>\n"
                "Пожалуйста, попробуйте еще раз",
                parse_mode='HTML'
            )
            return CHATTING

    elif query.data == "gpt_ask_question":
        try:
            await query.message.reply_text(
                "💭 <b>Задайте ваш вопрос:</b>\n\n"
                "Я готов помочь вам с любым вопросом по выбранной теме.",
                parse_mode='HTML'
            )
            return CHATTING
        except Exception as e:
            logger.error(f"Ошибка при запросе вопроса: {e}")
            await query.message.reply_text(
                "😔 <b>Произошла ошибка</b>\n"
                "Пожалуйста, попробуйте еще раз",
                parse_mode='HTML'
            )
            return CHATTING

    elif query.data == "gpt_retry":
        try:
            await query.message.reply_text(
                "🔄 <b>Попробуйте задать вопрос еще раз:</b>\n\n"
                "Я постараюсь дать вам максимально полезный ответ.",
                parse_mode='HTML'
            )
            return CHATTING
        except Exception as e:
            logger.error(f"Ошибка при повторной попытке: {e}")
            await query.message.reply_text(
                "😔 <b>Произошла ошибка</b>\n"
                "Пожалуйста, попробуйте еще раз",
                parse_mode='HTML'
            )
            return CHATTING

    return CHATTING


# Создаем обработчики для GPT
gpt_handler = ConversationHandler(
    entry_points=[
        CommandHandler('gpt', gpt_command),
        CallbackQueryHandler(gpt_start, pattern='^gpt_interface$')
    ],
    states={
        CHATTING: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gpt_message),
            CallbackQueryHandler(gpt_topic_selected, pattern=r'^gpt_topic_'),
            CallbackQueryHandler(handle_gpt_callback, pattern=r'^gpt_')
        ]
    },
    fallbacks=[
        CommandHandler('gpt', gpt_command),
        CallbackQueryHandler(gpt_start, pattern='^gpt_interface$'),
        CallbackQueryHandler(handle_gpt_callback, pattern=r'^gpt_')
    ],
    per_chat=True,
    per_message=False,
    name="gpt_conversation"
)

# Добавляем обработчики в правильном порядке
# Сначала добавляем ConversationHandler'ы
application.add_handler(gpt_handler)
application.add_handler(business_handler)
application.add_handler(quiz_handler)

# Затем добавляем обработчики команд
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("gpt", gpt_command))
application.add_handler(CommandHandler("talk", talk))
application.add_handler(CommandHandler("fact", random_fact))
application.add_handler(CommandHandler("business", business_command))

# Добавляем обработчики для диалогов
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, talk_dialog))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gpt_dialog))

# Добавляем обработчики для кнопок
application.add_handler(CallbackQueryHandler(talk_button, pattern="^talk_.*"))
application.add_handler(CallbackQueryHandler(business_button, pattern="^business_interface$"))
application.add_handler(CallbackQueryHandler(fact_button, pattern="^(new_fact|new_fact_no_photo)$"))


# Добавляем обработчик ошибок
def error_handler(update, context):
    """Обработчик ошибок"""
    logger.error(f"Произошла ошибка: {context.error}")
    if update and update.effective_message:
        update.effective_message.reply_text(
            "😔 Произошла ошибка при обработке запроса.\n"
            "Пожалуйста, попробуйте еще раз или вернитесь в меню.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Вернуться в меню", callback_data="main_menu")
            ]])
        )


application.add_error_handler(error_handler)

# Запускаем бота
if __name__ == '__main__':
    application.run_polling(allowed_updates=Update.ALL_TYPES)

