import requests
import time
from datetime import datetime
import sys

# goes as pyTelegramBotAPI in requirements
import telebot

import config
from photogpsbot import log, db


class TelegramBot(telebot.TeleBot):
    """
    Adds a couple of useful methods to TeleBot object.
    """

    def __init__(self, token, threaded=True, skip_pending=False,
                 num_threads=2):
        super().__init__(token, threaded, skip_pending, num_threads)
        self.start_time = None

    def _run(self):
        """
        Make bot start polling
        :return: None
        """
        log.info('Starting photogpsbot...')
        # Keep bot receiving messages
        self.polling(none_stop=True, timeout=90)

    def start_bot(self):
        """
        Wrapper around self._run just for the sake of making it more reliable
        and reconnect in case of errors. And to store time when bot started to
        work
        :return: None
        """
        try:
            self.start_time = datetime.now()
            self._run()

        except requests.exceptions.ReadTimeout as e:
            log.error(e)
            self.stop_polling()
            log.warning('Pausing bot for 30 seconds...')
            time.sleep(30)
            log.warning('Try to start the bot again...')
            self._run()

    def turn_bot_off(self):
        """
        Safely turn the bot off, closing db and messaging to its admin

        :return:
        """

        self.send_message(chat_id=config.MY_TELEGRAM, text='bye')

        if db.disconnect():
            log.info('Please wait for a sec, bot is turning off...')
            self.stop_polling()
            log.info('Auf Wiedersehen! Bot is turned off.')
            sys.exit()
        else:
            log.error('Cannot stop bot.')
            self.send_message(chat_id=config.MY_TELEGRAM,
                              text='Cannot stop bot.')
