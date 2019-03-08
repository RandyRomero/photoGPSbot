from photogpsbot import bot, log_files
import config


def send_last_logs():
    logfile_list = log_files.get_list()
    with open(logfile_list[-1].path, 'r') as last_log_file:
        bot.send_message(chat_id=config.MY_TELEGRAM,
                         text=last_log_file.read()[-4000:])
