from util import send_photo, send_text, load_message, load_prompt
from osnov_servis.shared import dialog, chatgpt
import logging
from openai import OpenAI
import os
from typing import List, Dict, Union
from .web_search import search_web, format_search_results
import re
import base64
from io import BytesIO
import requests

logger = logging.getLogger(__name__)

WAITING_FOR_MESSAGE = 1

# Инициализация OpenAI клиента
client = OpenAI(api_key=os.getenv("CHATGPT_TOKEN"))

# Список для хранения истории сообщений
message_list = []


def set_prompt(prompt: str = None):
    """Устанавливает системный промпт для GPT"""
    global message_list
    message_list = []
    if prompt:
        message_list.append({"role": "system", "content": prompt})
    else:
        message_list.append({
            "role": "system",
            "content": """Вы - умный ассистент с возможностью анализа изображений и поиска в интернете.
            При работе с изображениями:
            1. Внимательно анализируйте все детали на изображении
            2. Описывайте то, что видите, максимально подробно
            3. Если видите текст - воспроизводите его
            4. Если видите математические формулы или задачи - решайте их
            5. Если видите код - анализируйте его и предлагайте улучшения
            6. Если видите графики или диаграммы - интерпретируйте их
            7. Если видите ошибки или проблемы - предлагайте решения

            При ответе на вопросы:
            1. Если вопрос требует актуальной информации - используйте поиск в интернете
            2. Если вопрос о текущих событиях - обязательно проверяйте последние новости
            3. Если вопрос о фактах или данных - уточняйте актуальность информации
            4. Всегда указывайте источники информации
            5. Если информация может быть устаревшей - предупреждайте об этом
            6. Используйте поиск для подтверждения или опровержения информации"""
        })


def should_search_web(text: str) -> bool:
    """
    Определяет, нужно ли искать информацию в интернете

    Args:
        text (str): Текст запроса

    Returns:
        bool: True если нужен поиск, False если нет
    """
    # Ключевые слова для поиска
    search_keywords = [
        "найди", "поищи", "актуально", "сейчас", "новости", "последние",
        "сегодня", "вчера", "недавно", "текущий", "текущая", "текущее",
        "как дела", "что нового", "что происходит", "тренды", "статистика",
        "данные", "информация", "факты", "события", "происшествия"
    ]

    # Проверяем наличие ключевых слов
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in search_keywords):
        return True

    # Проверяем наличие временных маркеров
    time_patterns = [
        r'\b(сегодня|вчера|завтра|сейчас|недавно|в этом году|в этом месяце)\b',
        r'\b(202[0-9]|202[0-9])\b',  # Годы
        r'\b(январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)\b'
    ]

    if any(re.search(pattern, text_lower) for pattern in time_patterns):
        return True

    return False


def extract_search_query(text: str) -> str:
    """
    Извлекает поисковый запрос из текста пользователя

    Args:
        text (str): Текст запроса пользователя

    Returns:
        str: Оптимизированный поисковый запрос
    """
    # Удаляем общие фразы
    text = re.sub(r'\b(пожалуйста|мог бы ты|не мог бы ты|расскажи|скажи|подскажи)\b', '', text.lower())

    # Удаляем знаки препинания
    text = re.sub(r'[.,!?]', '', text)

    # Удаляем лишние пробелы
    text = ' '.join(text.split())

    return text


async def get_image_base64(image_url: str) -> str:
    """
    Получает base64 представление изображения по URL

    Args:
        image_url (str): URL изображения

    Returns:
        str: base64 строка изображения
    """
    try:
        response = requests.get(image_url)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении изображения: {e}")
        return None


async def analyze_image(image_url: str, prompt: str = None) -> str:
    """
    Анализирует изображение с помощью GPT-4 Vision

    Args:
        image_url (str): URL изображения
        prompt (str, optional): Дополнительный промпт для анализа

    Returns:
        str: Результат анализа изображения
    """
    try:
        # Получаем base64 изображения
        image_base64 = await get_image_base64(image_url)
        if not image_base64:
            return "Не удалось получить изображение для анализа."

        # Формируем сообщение для GPT
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt or "Проанализируй это изображение и опиши, что ты видишь. Если есть текст, формулы, код или графики - проанализируй их."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]

        # Получаем ответ от GPT
        response = client.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=messages,
            max_tokens=1000
        )

        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при анализе изображения: {e}")
        return "Произошла ошибка при анализе изображения."


async def gpt(text: str, image_url: str = None) -> str:
    """
    Отправляет запрос к GPT и получает ответ

    Args:
        text (str): Текст запроса
        image_url (str, optional): URL изображения для анализа

    Returns:
        str: Ответ от GPT
    """
    try:
        # Если есть изображение, анализируем его
        if image_url:
            image_analysis = await analyze_image(image_url, text)
            message_list.append({
                "role": "user",
                "content": f"Запрос: {text}\n\nАнализ изображения:\n{image_analysis}"
            })
        else:
            message_list.append({"role": "user", "content": text})

        # Проверяем, нужен ли поиск в интернете
        if should_search_web(text):
            # Извлекаем поисковый запрос
            search_query = extract_search_query(text)

            # Выполняем поиск
            search_results = await search_web(search_query, max_results=5)
            if search_results:
                # Добавляем результаты поиска в контекст
                search_context = format_search_results(search_results)
                message_list.append({
                    "role": "system",
                    "content": f"""Вот актуальная информация из интернета:

{search_context}

Используй эту информацию для ответа на вопрос пользователя. 
Важно:
1. Укажи источники информации
2. Если информация может быть неактуальной - предупреди об этом
3. Если нашел противоречивую информацию - укажи это
4. Если информация неполная - скажи об этом"""
                })

        # Получаем ответ от GPT
        response = client.chat.completions.create(
            model="gpt-4-vision-preview" if image_url else "gpt-3.5-turbo",
            messages=message_list,
            temperature=0.7,
            max_tokens=1000
        )

        # Получаем ответ
        answer = response.choices[0].message.content

        # Добавляем ответ в историю
        message_list.append({"role": "assistant", "content": answer})

        return answer
    except Exception as e:
        logger.error(f"Ошибка при работе с GPT: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."


async def gpt_command(update, context):
    """Обработчик команды /gpt"""
    dialog.mode = "gpt"
    text = load_message("gpt")
    await send_photo(update, context, "gpt")
    await send_text(update, context, text)
    # Устанавливаем промпт для GPT
    set_prompt(load_prompt("gpt"))


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
            set_prompt(system_prompt)
        return await gpt(prompt)
    except Exception as e:
        logger.error(f"Ошибка при получении ответа от ChatGPT: {e}")
        return "Извините, произошла ошибка при обработке запроса."







