import socket

# telebot goes as pyTelegramBotAPI in requirements
from telebot import apihelper
import config
from photogpsbot.handle_logs import CustomLogging

custom_logging = CustomLogging()
log = custom_logging.get_logger()

from photogpsbot.db_connector import DB
db = DB()

from photogpsbot.bot import TelegramBot
bot = TelegramBot(config.TELEGRAM_TOKEN)

if not socket.gethostname() == config.PROD_HOST_NAME:
    log.info('Working through proxy.')
    apihelper.proxy = {'https': config.PROXY_CONFIG}
