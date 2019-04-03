"""
Initiating essential modules for photoGPSbot
"""

import logging
import socket
import json

# Load file with messages for user in two languages
with open('photogpsbot/language_pack.json', 'r', encoding='utf8') as json_file:
    messages = json.load(json_file)

# telebot goes as pyTelegramBotAPI in requirements
from telebot import apihelper

import config
from photogpsbot.custom_logging import log, LogFiles, TelegramHandler
log_files = LogFiles()

from photogpsbot.bot import TelegramBot
bot = TelegramBot(config.TELEGRAM_TOKEN)

# set up and add a special handler to the logger so that the logger can send
# last logs to admin via the same Telegram bot
telegram_handler = TelegramHandler(bot)
telegram_handler.setLevel(logging.ERROR)
log.addHandler(telegram_handler)

from photogpsbot.db_connector import Database
db = Database()

from photogpsbot.users import User, Users
users = Users()

if not socket.gethostname() == config.PROD_HOST_NAME:
    log.info('Working through proxy.')
    apihelper.proxy = {'https': config.PROXY_CONFIG}
