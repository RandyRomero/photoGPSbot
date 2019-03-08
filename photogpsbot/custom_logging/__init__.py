"""
Initiating custom logging package
"""

from photogpsbot.custom_logging.logger import make_custom_logger
log = make_custom_logger()

from photogpsbot.custom_logging.log_files_handler import LogFiles
log_files = LogFiles()
