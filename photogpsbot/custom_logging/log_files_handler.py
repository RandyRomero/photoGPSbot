"""
Module to manage text log files that bot creates one by one every time it
starts.
"""

import os
import re
from collections import namedtuple
import time
from datetime import datetime

import send2trash

from photogpsbot.custom_logging import log


class LogFiles:
    """
    Helps to manage log files in a log folder. Like check size of logs,
    clean the log folder if there are to many logs, and just making list
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
        log file
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
                    datetime.strptime(date_from_filename,
                                      '%Y-%m-%d__%Hh%Mm').timetuple())
                # creation_time = time.mktime(creation_time.timetuple())
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
        :return:
        """
        logfile_list = self.get_list()
        total_size = 0
        if logfile_list:
            for file in logfile_list:
                total_size += file.size

        self.log.info('There is %.2f MB of logs.\n' % (total_size / 1024**2))

        return total_size

    def clean_log_folder(self, max_size):
        """
        Remove oldest log files from the log folder when
        size of folder is more than max_size.

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
        i = -1
        while total_size > max_size * 1024**2:
            # if folder with log files weighs more than max_size in megabytes -
            # recursively remove oldest one one by one
            logfile_to_delete = logfile_list[-i]
            i -= 1

            self.log.info('Removing old log file: %s',
                          logfile_to_delete.path)

            send2trash.send2trash(logfile_to_delete.path)
            # remove item from from list and subtract it's size from total size
            total_size -= logfile_to_delete.size
            logfile_list.remove(logfile_to_delete)

        self.logfile_list = self.get_list()
