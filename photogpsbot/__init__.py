"""
Initiating essential modules for photoGPSbot
"""

import socket
import json

# Load file with messages for user in two languages
with open('photogpsbot/language_pack.json', 'r', encoding='utf8') as json_file:
    messages = json.load(json_file)

# telebot goes as pyTelegramBotAPI in requirements
from telebot import apihelper

import config
from photogpsbot.custom_logging import log, log_files
from photogpsbot.bot import TelegramBot

bot = TelegramBot(config.TELEGRAM_TOKEN)

from photogpsbot.helper import send_last_logs
from photogpsbot.db_connector import Database
db = Database()

from photogpsbot.users import Users
users = Users()

if not socket.gethostname() == config.PROD_HOST_NAME:
    log.info('Working through proxy.')
    apihelper.proxy = {'https': config.PROXY_CONFIG}
