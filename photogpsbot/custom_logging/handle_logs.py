"""
This is a module that makes a new logger for your script that log sto file and
console from all your modules.

In order to use it in you script you need to do next steps:
import CustomLogging from handle_logs, then:

custom_logging = CustomLogging()
log = custom_logging.get_logger()

Then when you want to log something you type for example:
log.debug('You debugging message') or log.info('User went crazy!')

This module can also clean up log folder when it is too large. In order to do
that call custom_logging.clean_log_folder(size) where size is integer that
represents maximum size in megabytes that triggers removing the oldest
log files.

Written by Aleksandr Mikheev a.k.a Randy Romero
https://github.com/RandyRomero

"""