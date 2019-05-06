"""
Use this module to get the bot to work and communicate with Telegram servers
"""


import requests
import time
from datetime import datetime
import sys
from typing import Optional

# goes as pyTelegramBotAPI in requirements
import telebot  # type: ignore

import config
from photogpsbot import log


class TelegramBot(telebot.TeleBot):
    """
    Adds a couple of useful methods to TeleBot object for restating bot in
    case of errors for example
    """

    def __init__(self, token: str,
                 threaded: bool = True,
                 skip_pending: bool = False,
                 num_threads: int = 2) -> None:

        super().__init__(token, threaded, skip_pending, num_threads)
        self.start_time: Optional[datetime] = None

    def _run(self) -> None:
        """
        Make bot start polling

        :return: None
        """
        log.info('Starting photogpsbot...')
        # Keep bot receiving messages
        self.polling(none_stop=True, timeout=90)

    def start_bot(self) -> None:
        """
        Method to get the bot started

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

    def turn_off(self) -> None:
        """
        Safely turn the bot off and message to its admin

        :return: None
        """

        self.send_message(chat_id=config.MY_TELEGRAM, text='bye')
        log.info('Please wait for a sec, bot is turning off...')
        self.stop_polling()
        log.info('Auf Wiedersehen! Bot is turned off.')
        sys.exit()

    def __str__(self) -> str:
        return ('Instance of a Telegram bot. '
                f'Started connection '
                f'at {self.start_time.strftime("%Y-%m-%d %H:%M:%S")}.')

