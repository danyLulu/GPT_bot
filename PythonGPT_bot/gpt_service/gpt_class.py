import openai
from openai import OpenAI
import httpx as httpx
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any
import speech_recognition as sr
from gtts import gTTS
import tempfile
from pydub import AudioSegment
import logging
import sys
import shutil
import subprocess
import time
import glob

logger = logging.getLogger(__name__)


def get_ffmpeg_path():
    """Получает путь к ffmpeg"""
    # Проверяем локальную установку
    base_dir = os.path.dirname(os.path.dirname(__file__))
    local_ffmpeg = os.path.join(base_dir, 'bin', 'ffmpeg-master-latest-win64-gpl', 'bin', 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg):
        logger.info(f"ffmpeg найден локально: {local_ffmpeg}")
        return local_ffmpeg

    # Проверяем системный ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        logger.info(f"ffmpeg найден в системе: {ffmpeg_path}")
        return ffmpeg_path

    # Проверяем стандартные пути установки
    standard_paths = [
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
        os.path.expanduser('~\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*\\ffmpeg\\bin\\ffmpeg.exe')
    ]

    for path in standard_paths:
        if '*' in path:
            # Для путей с wildcard
            matches = glob.glob(path)
            if matches:
                logger.info(f"ffmpeg найден в стандартном пути: {matches[0]}")
                return matches[0]
        elif os.path.exists(path):
            logger.info(f"ffmpeg найден в стандартном пути: {path}")
            return path

    logger.error("ffmpeg не найден ни в одном из возможных мест")
    return None


def setup_ffmpeg():
    """Настраивает ffmpeg"""
    try:
        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            # Добавляем путь к ffmpeg в PATH
            ffmpeg_dir = os.path.dirname(ffmpeg_path)
            if ffmpeg_dir not in os.environ['PATH']:
                os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ['PATH']
            logger.info(f"ffmpeg настроен: {ffmpeg_path}")
            return True

        logger.error("Не удалось найти ffmpeg")
        return False

    except Exception as e:
        logger.error(f"Ошибка при настройке ffmpeg: {e}")
        return False


# Инициализируем ffmpeg при импорте модуля
if not setup_ffmpeg():
    logger.error("Не удалось настроить ffmpeg. Голосовые функции могут не работать.")

load_dotenv()


class GPTClient:
    def __init__(self, api_key: str, proxies: Optional[Dict[str, str]] = None):
        """
        Инициализация клиента GPT

        Args:
            api_key (str): API ключ OpenAI
            proxies (Optional[Dict[str, str]]): Словарь с прокси
        """
        self.api_key = api_key

        # Настройка транспорта с прокси
        transport = None
        if proxies:
            try:
                # Создаем транспорт с прокси
                transport = httpx.HTTPTransport(
                    proxy=httpx.Proxy(proxies.get("http", proxies.get("https")))
                )
            except Exception as e:
                print(f"Ошибка при настройке прокси: {e}")
                transport = None

        # Инициализация клиента OpenAI
        self.client = OpenAI(
            api_key=api_key,
            http_client=httpx.Client(transport=transport) if transport else None
        )

        # История сообщений
        self.message_history = []

    def add_message(self, role: str, content: str):
        """
        Добавление сообщения в историю

        Args:
            role (str): Роль отправителя (system/user/assistant)
            content (str): Содержание сообщения
        """
        self.message_history.append({"role": role, "content": content})

    def clear_history(self):
        """Очистка истории сообщений"""
        self.message_history = []

    def get_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Получение ответа от GPT

        Args:
            prompt (str): Запрос пользователя
            system_prompt (Optional[str]): Системный промпт

        Returns:
            str: Ответ от GPT
        """
        try:
            # Очищаем историю если есть системный промпт
            if system_prompt:
                self.clear_history()
                self.add_message("system", system_prompt)

            # Добавляем запрос пользователя
            self.add_message("user", prompt)

            # Получаем ответ от GPT
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=self.message_history,
                temperature=0.7,
                max_tokens=1000
            )

            # Получаем текст ответа
            answer = response.choices[0].message.content

            # Добавляем ответ в историю
            self.add_message("assistant", answer)

            return answer

        except Exception as e:
            print(f"Ошибка при получении ответа от GPT: {e}")
            return "Извините, произошла ошибка при обработке запроса."


class ChatGptService:
    client: OpenAI = None
    message_list: list = None

    def __init__(self, token):
        if not token:
            raise ValueError("CHATGPT_TOKEN не установлен в переменных окружения")

        token = "sk-proj-" + token[:3:-1] if token.startswith('gpt:') else token

        # Настройка прокси
        proxies = {
            "http": "http://18.199.183.77:49232",
            "https": "http://18.199.183.77:49232"
        }

        try:
            # Создаем транспорт с прокси
            transport = httpx.HTTPTransport(
                proxy=httpx.Proxy(proxies["http"])
            )

            # Инициализируем клиент с прокси
            self.client = openai.OpenAI(
                api_key=token,
                http_client=httpx.Client(transport=transport)
            )
        except Exception as e:
            print(f"Ошибка при настройке прокси: {e}")
            # Если прокси не работает, создаем клиент без прокси
            self.client = openai.OpenAI(api_key=token)

        self.message_list = []

    async def send_message_list(self) -> str:
        completion = self.client.chat.completions.create(
            model="gpt-4",  # Изменено с gpt-4o-mini на gpt-4
            messages=self.message_list,
            max_tokens=3000,
            temperature=0.9
        )
        message = completion.choices[0].message
        self.message_list.append(message)
        return message.content

    def set_prompt(self, prompt_text: str) -> None:
        self.message_list.clear()
        self.message_list.append({"role": "system", "content": prompt_text})

    async def add_message(self, message_text: str) -> str:
        self.message_list.append({"role": "user", "content": message_text})
        return await self.send_message_list()

    async def send_question(self, prompt_text: str, message_text: str) -> str:
        self.message_list.clear()
        self.message_list.append({"role": "system", "content": prompt_text})
        self.message_list.append({"role": "user", "content": message_text})
        return await self.send_message_list()


def safe_remove_file(file_path: str, max_retries: int = 3, delay: float = 0.1):
    """Безопасное удаление файла с повторными попытками"""
    for i in range(max_retries):
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Файл {file_path} успешно удален")
            return True
        except Exception as e:
            logger.warning(f"Попытка {i + 1} удаления файла {file_path} не удалась: {e}")
            time.sleep(delay)
    return False


def run_ffmpeg(input_path: str, output_path: str, input_format: str = None, output_format: str = None):
    """Запускает ffmpeg для конвертации аудио"""
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg не найден")

    cmd = [
        ffmpeg_path,
        '-y',  # Перезаписывать выходной файл
        '-i', input_path
    ]

    if input_format:
        cmd.extend(['-f', input_format])

    cmd.extend([
        '-acodec', 'pcm_s16le' if output_format == 'wav' else 'libvorbis',
        '-ac', '1',  # Моно
        '-ar', '16k',  # Частота дискретизации
        output_path
    ])

    logger.info(f"Запускаем ffmpeg с командой: {' '.join(cmd)}")

    try:
        # Используем subprocess.run с кодировкой utf-8
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        logger.info("ffmpeg выполнен успешно")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка ffmpeg: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запуске ffmpeg: {e}")
        raise


async def speech_to_text(audio_data: bytes) -> str:
    """
    Конвертирует голосовое сообщение в текст

    Args:
        audio_data (bytes): Голосовое сообщение в формате bytes

    Returns:
        str: Распознанный текст
    """
    # Создаем временную директорию в текущей директории проекта
    base_dir = os.path.dirname(os.path.dirname(__file__))
    temp_dir = os.path.join(base_dir, 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    # Создаем уникальные имена файлов
    timestamp = int(time.time() * 1000)
    temp_oga_path = os.path.join(temp_dir, f'input_{timestamp}.oga')
    wav_path = os.path.join(temp_dir, f'output_{timestamp}.wav')

    logger.info(f"Создаем временные файлы: {temp_oga_path}, {wav_path}")

    try:
        # Сохраняем входной файл
        with open(temp_oga_path, 'wb') as f:
            f.write(audio_data)
        logger.info(f"Входной файл сохранен: {temp_oga_path}")

        # Проверяем, что файл создан и доступен
        if not os.path.exists(temp_oga_path):
            raise FileNotFoundError(f"Входной файл {temp_oga_path} не был создан")

        # Конвертируем OGA в WAV используя ffmpeg
        try:
            logger.info("Начинаем конвертацию OGA в WAV...")
            run_ffmpeg(temp_oga_path, wav_path, input_format='ogg', output_format='wav')
        except Exception as e:
            logger.error(f"Ошибка при конвертации: {e}")
            raise

        # Проверяем, что файл создан и доступен
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"WAV файл {wav_path} не был создан")
        logger.info(f"WAV файл создан: {wav_path}")

        # Инициализируем распознаватель речи
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300  # Уменьшаем порог для лучшего распознавания

        # Распознаем речь
        logger.info("Начинаем распознавание речи...")
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data, language='ru-RU')
                logger.info("Речь успешно распознана")
                return text
            except sr.UnknownValueError:
                logger.error("Речь не распознана")
                return None
            except sr.RequestError as e:
                logger.error(f"Ошибка сервиса распознавания: {e}")
                return None

    except Exception as e:
        logger.error(f"Ошибка при распознавании речи: {e}")
        return None

    finally:
        # Удаляем временные файлы
        logger.info("Удаляем временные файлы...")
        try:
            safe_remove_file(temp_oga_path)
            safe_remove_file(wav_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении временных файлов: {e}")


async def text_to_speech(text: str) -> bytes:
    """
    Конвертирует текст в голосовое сообщение

    Args:
        text (str): Текст для конвертации

    Returns:
        bytes: Голосовое сообщение в формате bytes
    """
    # Создаем временную директорию в текущей директории проекта
    base_dir = os.path.dirname(os.path.dirname(__file__))
    temp_dir = os.path.join(base_dir, 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    # Создаем уникальные имена файлов
    timestamp = int(time.time() * 1000)
    temp_mp3_path = os.path.join(temp_dir, f'input_{timestamp}.mp3')
    ogg_path = os.path.join(temp_dir, f'output_{timestamp}.ogg')

    logger.info(f"Создаем временные файлы: {temp_mp3_path}, {ogg_path}")

    try:
        # Генерируем речь
        logger.info("Генерируем речь...")
        tts = gTTS(text=text, lang='ru', slow=False)
        tts.save(temp_mp3_path)
        logger.info(f"MP3 файл создан: {temp_mp3_path}")

        # Проверяем, что файл создан и доступен
        if not os.path.exists(temp_mp3_path):
            raise FileNotFoundError(f"MP3 файл {temp_mp3_path} не был создан")

        # Конвертируем MP3 в OGG используя ffmpeg
        try:
            logger.info("Начинаем конвертацию MP3 в OGG...")
            run_ffmpeg(temp_mp3_path, ogg_path, input_format='mp3', output_format='ogg')
        except Exception as e:
            logger.error(f"Ошибка при конвертации: {e}")
            raise

        # Проверяем, что файл создан и доступен
        if not os.path.exists(ogg_path):
            raise FileNotFoundError(f"OGG файл {ogg_path} не был создан")
        logger.info(f"OGG файл создан: {ogg_path}")

        # Читаем OGG файл
        with open(ogg_path, 'rb') as f:
            ogg_data = f.read()
        logger.info("OGG файл успешно прочитан")

        return ogg_data

    except Exception as e:
        logger.error(f"Ошибка при генерации речи: {e}")
        return None

    finally:
        # Удаляем временные файлы
        logger.info("Удаляем временные файлы...")
        try:
            safe_remove_file(temp_mp3_path)
            safe_remove_file(ogg_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении временных файлов: {e}")
