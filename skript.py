import json
from telethon import TelegramClient, events
from telethon.errors import ChannelPrivateError, FloodWaitError, MessageNotModifiedError, ChannelInvalidError, RPCError
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    MessageMediaPoll, MessageMediaDice, MessageMediaUnsupported
)
import time
import logging
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация через файл cfg.json
config_file = 'cfg.json'

# Проверяем существование файла
if not os.path.exists(config_file):
    raise FileNotFoundError(f"Файл конфигурации '{config_file}' не найден.")

# Чтение содержимого файла перед парсингом
with open(config_file, 'r', encoding='utf-8') as f:
    file_content = f.read()
    logger.info("Содержимое файла cfg.json:")
    logger.info(file_content)

# Парсинг файла конфигурации
try:
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
except json.JSONDecodeError as e:
    logger.error(f"Ошибка при чтении файла конфигурации: {e}")
    logger.error(f"Содержимое файла cfg.json (ещё раз):")
    logger.error(file_content)
    raise ValueError(f"Ошибка при чтении файла конфигурации: {e}")

# Проверяем наличие всех необходимых ключей
required_keys = ['api_id', 'api_hash', 'phone_number', 'source_channel', 'target_channel']
missing_keys = [key for key in required_keys if key not in config]

if missing_keys:
    raise KeyError(f"Отсутствуют следующие ключи в файле конфигурации: {', '.join(missing_keys)}")

api_id = config['api_id']  # Получите на сайте my.telegram.org
api_hash = config['api_hash']
phone_number = config['phone_number']
source_channel = config['source_channel']
target_channel = config['target_channel']

client = TelegramClient('session_name', api_id, api_hash)

# Создаем директорию для загрузки медиафайлов, если она не существует
downloads_dir = 'downloads'
if not os.path.exists(downloads_dir):
    os.makedirs(downloads_dir)

async def get_entity(client, channel_identifier):
    try:
        entity = await client.get_entity(channel_identifier)
        return entity
    except Exception as e:
        logger.error(f"Ошибка при получении канала {channel_identifier}: {e}")
        return None

async def find_channel_by_id_or_username(client, channel_identifier):
    try:
        entity = await client.get_entity(channel_identifier)
        return entity
    except Exception as e:
        logger.error(f"Ошибка при поиске канала {channel_identifier}: {e}")
        dialogs = await client.get_dialogs()

        for dialog in dialogs:
            if str(dialog.id) == channel_identifier:
                return dialog.entity
            elif hasattr(dialog.entity, 'username') and dialog.entity.username == channel_identifier.lstrip('@'):
                return dialog.entity

        logger.error(f"Канал с идентификатором {channel_identifier} не найден.")
        return None

async def copy_posts(source_channel, target_channel, max_depth=5):
    source_entity = await find_channel_by_id_or_username(client, source_channel)
    target_entity = await find_channel_by_id_or_username(client, target_channel)

    if not source_entity or not target_entity:
        logger.error("Не удалось получить один из каналов.")
        return

    # Получаем сообщения из исходного канала
    messages = await client.get_messages(source_entity, limit=1000)
    for msg in messages:
        # Проверяем, если сообщение содержит медиа или текст
        media = msg.media
        text = msg.text or ""
        
        if media:
            if isinstance(media, MessageMediaPhoto):
                file_path = await client.download_media(media, file=os.path.join(downloads_dir, f"{msg.id}.jpg"))
                if file_path:
                    await client.send_file(target_entity, file_path, caption=text)
                    logger.info(f"Сообщение с ID {msg.id} скопировано.")
                    os.remove(file_path)  # Удаляем временный файл после отправки
                else:
                    logger.warning(f"Не удалось загрузить медиа для сообщения с ID {msg.id}")
            elif isinstance(media, MessageMediaDocument):
                file_ext = media.document.mime_type.split('/')[-1] if media.document.mime_type else 'unknown'
                file_path = await client.download_media(media, file=os.path.join(downloads_dir, f"{msg.id}.{file_ext}"))
                if file_path:
                    await client.send_file(target_entity, file_path, caption=text)
                    logger.info(f"Сообщение с ID {msg.id} скопировано.")
                    os.remove(file_path)  # Удаляем временный файл после отправки
                else:
                    logger.warning(f"Не удалось загрузить медиа для сообщения с ID {msg.id}")
            elif isinstance(media, MessageMediaWebPage):
                if media.webpage.type == 'photo':
                    file_path = await client.download_media(media.webpage.photo, file=os.path.join(downloads_dir, f"{msg.id}.jpg"))
                    if file_path:
                        await client.send_file(target_entity, file_path, caption=text)
                        logger.info(f"Сообщение с ID {msg.id} скопировано.")
                        os.remove(file_path)  # Удаляем временный файл после отправки
                    else:
                        logger.warning(f"Не удалось загрузить медиа для сообщения с ID {msg.id}")
                else:
                    await client.send_message(target_entity, text)
                    logger.info(f"Текстовое сообщение с ID {msg.id} скопировано.")
            else:
                logger.warning(f"Не поддерживающийся тип медиа: {type(media)}")
                await client.send_message(target_entity, text)
        else:
            await client.send_message(target_entity, text)
            logger.info(f"Текстовое сообщение с ID {msg.id} скопировано.")

        # Добавляем небольшую задержку, чтобы избежать FloodWaitError
        time.sleep(1)

async def check_channels():
    await client.start(phone_number)
    try:
        source_entity = await find_channel_by_id_or_username(client, source_channel)
        target_entity = await find_channel_by_id_or_username(client, target_channel)
        if source_entity:
            print(f"Source channel found: {source_entity.title} ({source_entity.id})")
        else:
            print(f"Source channel not found: {source_channel}")
        
        if target_entity:
            print(f"Target channel found: {target_entity.title} ({target_entity.id})")
        else:
            print(f"Target channel not found: {target_channel}")
    except Exception as e:
        logger.error(f"Ошибка при проверке каналов: {e}")

async def main():
    await client.start(phone_number)
    # Пример копирования постов из одного канала в другой
    source_channel = config["source_channel"]
    target_channel = config["target_channel"]

    # Проверяем доступность каналов
    await check_channels()

    # Копируем сообщения
    await copy_posts(source_channel, target_channel)

# Запуск клиента Telethon
with client:
    client.loop.run_until_complete(main())