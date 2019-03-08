"""
This is a module that makes a new logger for your script that log sto file and
console from all your modules.

In order to use it in you script you need to do next steps:
import make_custom_logger() from this custom_logging package
then call make_custom_logger to get the instance of a logger (more or less
standart Python logging from >> logging << module with a couple of custom
bicycles

from custom_logging.logger import make_custom_logger
log = make_custom_logger

Then when you want to log something you type for example:
log.debug('You debugging message') or log.info('User went crazy!')

"""

import time
import os
import logging


def make_custom_logger():

    log = None
    return_counter = 0
    log_folder = '../log'

    def make_new_logger():
        """
        Set up a new custom logger for using across modules of the bot
        :return: None
        """
        # __name__ needs to add name of corresponding module in log message
        new_log = logging.getLogger(__name__)
        new_log.setLevel(logging.DEBUG)  # set level of messages to be logged

        # Define format of logging messages
        formatter = logging.Formatter('%(levelname)s %(asctime)s %(module)s'
                                      ' line %(lineno)s: %(message)s')

        # Define time format to add to a name of a new log file
        timestr = time.strftime('%Y-%m-%d__%Hh%Mm')
        new_log_name = os.path.join(log_folder, f'log_{timestr}.txt')

        # create new log every time when script starts instead of writing
        # in the same file
        if os.path.exists(log_folder):
            # if log file with this date already exists,
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

    if return_counter == 0:
        return_counter += 1
        log = make_new_logger()
        return log
    else:
        return log
