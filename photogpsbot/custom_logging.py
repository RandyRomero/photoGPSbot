"""
This is a module that sets up a custom logger for the Telegram bot; this
logger will write messages to the stdout, to the text files within ./log folder
and also it will send messages to the admin of the bot in case of ERROR level
of the log message

Also there is a special class to handle log files and another one that is an
extension for StreamHandler for logger that provides a way to send
the last N symbols of the last log file to the admin via Telegram. You have to
add this TelegramHandler to the logger after initiating the bot

"""

import time
import os
import logging
from collections import namedtuple
import re
from datetime import datetime as dt, timedelta as td

import send2trash

import config


def make_custom_logger():
    """
    Set up a new custom logger for using across modules of the bot
    :return: new logging.Logger() instance
    """

    log_folder = './log'

    # __name__ needs to add name of corresponding module in a log message
    new_log = logging.getLogger(__name__)
    new_log.setLevel(logging.DEBUG)  # set level of messages to be logged

    # Define format of logging messages
    formatter = logging.Formatter('%(levelname)s %(asctime)s %(module)s'
                                  ' line %(lineno)s: %(message)s')

    # Define the time format to add to a name of a new log file
    timestr = time.strftime('%Y-%m-%d__%Hh%Mm')
    new_log_name = os.path.join(log_folder, f'log_{timestr}.txt')

    # create new log every time when script starts instead of writing
    # in the same file
    if os.path.exists(log_folder):
        # if a log file with this date already exists,
        # make new one with (i) in the name
        if os.path.exists(new_log_name):
            i = 2
            filename = f'log_{timestr}({i}).txt'
            while os.path.exists(os.path.join('log', filename)):
                i += 1
                continue
            file_handler = logging.FileHandler(
                os.path.join(log_folder, filename),
                encoding='utf8')
        else:
            file_handler = logging.FileHandler(new_log_name,
                                               encoding='utf8')
    else:
        os.mkdir(log_folder)
        file_handler = logging.FileHandler(new_log_name, encoding='utf8')

    # set format to both handlers
    stream_handler = logging.StreamHandler()

    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # apply handler to this module
    new_log.addHandler(file_handler)
    new_log.addHandler(stream_handler)

    return new_log


log = make_custom_logger()


class LogFiles:
    """
    Helps to manage log files in a log folder. Checks size of logs,
    cleans the log folder if there are to many logs, makes list
    of log files with their path, size and date and time of creation
    """
    def __init__(self):
        self.log = log
        self.log_folder = './log'
        self.LogFile = namedtuple('LogFile', 'path, creation_time, size')
        self.logfile_list = []

    def get_list(self):
        """
        Looks in the log folder and count every log file, add them all to
        a list
        :return: a list of named tuples where each represents one
        log file with its properties. Sorted by the time of creation of each
        log file - the oldest is the 0th in the list and the newest is [-1]
        """

        logfile_list = []
        # Get name and creation time of every logfile
        for root, subfolders, logfiles in os.walk(self.log_folder):
            if not logfiles:
                return []
            for logfile in logfiles:
                # Get date and time as a string from a file name
                regex = re.compile(r'(\d{4}-\d{2}-\d{2}__\d{2}h\d{2}m)')
                date_from_filename = re.search(regex, logfile).group()
                # Covert string with date and time to timestamp
                creation_time = time.mktime(
                    dt.strptime(date_from_filename,
                                      '%Y-%m-%d__%Hh%Mm').timetuple())
                path_to_logfile = os.path.join(root, logfile)
                size_of_log = os.path.getsize(path_to_logfile)

                logfile_list.append(
                    self.LogFile(path=path_to_logfile,
                                 creation_time=creation_time,
                                 size=size_of_log))

            return sorted(logfile_list, key=lambda x: x.creation_time)

    def _count_total_size(self):
        """
        Counts size of all log files in the log folder
        :return: total size of all log files as a float
        """
        logfile_list = self.get_list()
        total_size = 0
        if logfile_list:
            for file in logfile_list:
                total_size += file.size

        return total_size / 1024**2

    def clean_log_folder(self, max_size):
        """
        Remove the oldest log files from the log folder when the
        size of the folder is more than max_size.

        Script takes creation time of file not from its properties (get.cwd()),
        but from it's name, because you cannot rely on
        properties in case if log file was copied by
        for example Yandex.Disk, because then creation time is
        time of copying this file from another machine
        :param max_size: integer that represents threshold after which this
        function will start to delete old log files
        :return: None
        """

        logfile_list = self.get_list()
        total_size = self._count_total_size()
        while total_size > max_size:
            # if folder with log files weighs more than max_size in megabytes -
            # recursively remove the oldest one one by one
            logfile_to_delete = logfile_list[1]

            self.log.info('Removing old log file: %s',
                          logfile_to_delete.path)

            # remove file from disk
            send2trash.send2trash(logfile_to_delete.path)
            # remove item from the list and subtract it's size from the
            # total size
            total_size -= logfile_to_delete.size
            logfile_list.remove(logfile_to_delete)

        self.logfile_list = self.get_list()

    def __str__(self):
        return (f'{self.__class__.__name__} instance. Log folder is '
                f'"{self.log_folder}". Now it handles {len(self.get_list())} '
                f'files with total size of {self._count_total_size():.2f} MB.')


class TelegramHandler(logging.StreamHandler):

    """
    An extension for the StreamHandler for logger that provides a way to send
    the last N symbols of the last log file to the admin via Telegram.
    You have to add this TelegramHandler to the logger after initiating the bot
    """

    def __init__(self, bot):
        super().__init__(self)
        # instance of TelegramBot to send messages via telegram
        self.bot = bot
        # time mark to make this method to send message via Telegram not more
        # than ones in 15 seconds
        self.send_time = dt.now() - td(seconds=15)
        self.log_files = LogFiles()

    def _send_last_logs(self):
        # Extract the last N symbols from the last log file
        logfile_list = self.log_files.get_list()
        with open(logfile_list[-1].path, 'r') as last_log_file:
            self.bot.send_message(chat_id=config.MY_TELEGRAM,
                                  text=last_log_file.read()[-4000:])

    def emit(self, record):
        if self.send_time + td(seconds=15) < dt.now():
            self._send_last_logs()
            self.send_time = dt.now()
