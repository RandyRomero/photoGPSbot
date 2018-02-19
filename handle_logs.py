#!python3
# -*- coding: utf-8 -*-

# Written by Aleksandr Mikheev a.k.a Randy Romero
# https://github.com/RandyRomero

# This is module that sets logger for your script that log to file and console from all your models.

# In order to use it in you script you need import log, clean_log_folder from handle_logs
# Then when you want to log something you type for example:
# log.debug('You debugging message') or log.info('User went crazy!')

# This module can also clean up log folder when it is too large
# In order to do that call clean_log_folder(size)
# where size is integer that represents maximum size in megabytes that
# triggers removing the oldest log files


import logging
import os
import time
import send2trash
from datetime import datetime
import re


def set_logger():
    new_log = logging.getLogger(__name__)  # __name__ needs to add name of corresponding module in log message
    new_log.setLevel(logging.DEBUG)  # set level of messages to be logged

    # Define format of logging messages
    formatter = logging.Formatter('%(levelname)s %(asctime)s %(module)s line %(lineno)s: %(message)s')

    # Define time format to add to a name of a new log file
    timestr = time.strftime('%Y-%m-%d__%Hh%Mm')
    new_log_name = os.path.join('log', 'log_' + timestr + '.txt')

    if os.path.exists('log'):  # create new log every time when script starts instead of writing in the same file
        if os.path.exists(new_log_name):  # if log file with this date already exists, make new one with (i) in the name
            i = 2
            while os.path.exists(os.path.join('log', 'log_' + timestr + '(' + str(i) + ').txt')):
                i += 1
                continue
            file_handler = logging.FileHandler(os.path.join('log', 'log_' + timestr + '(' +
                                                            str(i) + ').txt'), encoding='utf8')
        else:
            file_handler = logging.FileHandler(new_log_name, encoding='utf8')
    else:
        os.mkdir('log')
        file_handler = logging.FileHandler(new_log_name, encoding='utf8')

    # set format to both handlers
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # apply handler to this module
    new_log.addHandler(file_handler)
    new_log.addHandler(stream_handler)

    return new_log


def clean_log_folder(max_size):
    # Remove oldest log files from log folder when size of folder is more than max_size.

    # Script take creation time of file not from its properties (get.cwd()),
    # but from it's name, because you cannot rely on properties in case if log file was copied by
    # for example Yandex.Disk, because then creation time is time of copying this file from another machine

    logfile_list = []

    def check_logs_size():  # count size of all already existing logs and create a list of them
        nonlocal logfile_list
        total_size = 0

        for root, subfolders, logfiles in os.walk('log'):  # Get name and creation time of every logfile
            for logfile in logfiles:
                # Get date and time as a string from file name
                date_from_filename = re.search(r'(\d{4}-\d{2}-\d{2}__\d{2}h\d{2}m)', logfile).group()
                # Covert string with date and time to timestamp
                creation_time = time.mktime(datetime.strptime(date_from_filename, '%Y-%m-%d__%Hh%Mm').timetuple())
                # creation_time = time.mktime(creation_time.timetuple())
                path_to_logfile = os.path.join(root, logfile)
                size_of_log = os.path.getsize(path_to_logfile)
                logfile_list.append([path_to_logfile, creation_time, size_of_log])
                total_size += size_of_log

        log.info('There is {0:.02f} MB of logs.\n'.format(total_size / 1024**2))
        return total_size

    total_log_size = check_logs_size()

    while total_log_size > max_size * 1024**2:
        # if log files weighs more than max_size in megabytes - recursively remove oldest one one by one
        logfile_to_delete = ''
        oldest = time.time()

        # recursively check all log files to find out the oldest one
        for index, val in enumerate(logfile_list):  # enumerate to extract not only values, but their indexes also
            if val[1] < oldest:  # if file older than previous one
                oldest = val[1]
                logfile_to_delete = val[0]
                index_to_remove = index
        log.info('Removing old log file: ' + logfile_to_delete + ', ' +
                 str(datetime.fromtimestamp(oldest)))

        send2trash.send2trash(logfile_to_delete)
        # remove item from from list and subtract it's size from total size
        total_log_size -= logfile_list[index_to_remove][2]
        logfile_list.pop(index_to_remove)


log = set_logger()
