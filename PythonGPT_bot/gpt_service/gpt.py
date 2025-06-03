from util import send_photo, send_text, load_message, load_prompt
from osnov_servis.shared import dialog, chatgpt
import logging

logger = logging.getLogger(__name__)

WAITING_FOR_MESSAGE = 1


async def gpt(message_text: str) -> str:
    """
    Получает ответ от GPT на заданный вопрос.

    Args:
        message_text (str): Текст сообщения пользователя

    Returns:
        str: Ответ от GPT
    """
    try:
        # Если это первое сообщение, устанавливаем системный промпт
        if not chatgpt.message_list:
            chatgpt.set_prompt(load_prompt("gpt"))

        # Получаем ответ от GPT
        return await chatgpt.add_message(message_text)
    except Exception as e:
        logger.error(f"Ошибка в GPT: {e}")
        return "Извините, произошла ошибка при обработке запроса."


async def gpt_command(update, context):
    """Обработчик команды /gpt"""
    dialog.mode = "gpt"
    text = load_message("gpt")
    await send_photo(update, context, "gpt")
    await send_text(update, context, text)
    # Устанавливаем промпт для GPT
    chatgpt.set_prompt(load_prompt("gpt"))


async def gpt_dialog(update, context):
    """Обработчик диалога с GPT"""
    if dialog.mode != "gpt":
        return

    text = update.message.text

    # Показываем сообщение о генерации
    my_message = await send_text(update, context,
                                 "ChatGPT генерирует информацию. Это может занять несколько секунд...")

    try:
        # Получаем ответ от GPT
        answer = await gpt(text)
        await my_message.edit_text(answer)
    except Exception as e:
        logger.error(f"Error in GPT dialog: {e}")
        await my_message.edit_text("Извините, произошла ошибка при генерации ответа. Попробуйте еще раз.")


async def get_personality_response(prompt: str, system_prompt: str = None) -> str:
    """
    Получает ответ от ChatGPT с учетом личности.

    Args:
        prompt (str): Запрос пользователя
        system_prompt (str, optional): Системный промпт для определения личности

    Returns:
        str: Ответ от ChatGPT
    """
    try:
        if system_prompt:
            chatgpt.set_prompt(system_prompt)
        return await chatgpt.add_message(prompt)
    except Exception as e:
        logger.error(f"Ошибка при получении ответа от ChatGPT: {e}")
        return "Извините, произошла ошибка при обработке запроса."







