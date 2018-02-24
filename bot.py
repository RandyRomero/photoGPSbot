#!python3
# -*- coding: utf-8 -*-

# Small bot for Telegram that receive your photo and return you map where it was taken.
# Written by Aleksandr Mikheev.
# https://github.com/RandyRomero/map_returning_bot

import config
import telebot
from telebot import types
import exifread
import requests
from io import BytesIO
import traceback
from handle_logs import log, clean_log_folder
from language_pack import lang_msgs
import db_connector
import MySQLdb

log.info('Starting photoGPSbot...')
log.info('Cleaning log folder...')
clean_log_folder(20)

bot = telebot.TeleBot(config.token)
# TODO Make command to safely turn bot down when necessary (closing ssh and connection to db)

# Connect to db
db = db_connector.connect()
if not db:
    log.warning('Can\'t connect to db.')

# ping(True) checks whether or not the connection to the server is
# working. If it has gone down, an automatic reconnection is
# attempted.
db.ping(True)
cursor = db.cursor()

user_lang = {}


def load_last_user_languages(message):
    pass


def set_user_language(chat_id, lang):
    log.debug('Updating info about user {} language in memory & database...'.format(chat_id))
    query = 'UPDATE user_lang_table SET lang="{}" WHERE chat_id={}'.format(lang, chat_id)
    cursor.execute(query)
    db.commit()
    user_lang[chat_id] = lang
    log.info('User {} language was switched to {}'.format(chat_id, lang))


def get_user_lang(message):
    """
    Function to look up user language in dictionary (which is like cache), than in database (if it is not in dict),
    then set language according to language code from telegram message object
    :param message: telegram message object
    :return: language tag like ru-RU, en-US
    """
    log.debug('################ get user language debug info ################')
    chat_id = message.chat.id
    log.debug('Defining user {} language...'.format(chat_id))
    log.debug('Looking up in memory...')
    lang = user_lang.get(chat_id, None)
    if not lang:
        log.debug('There is no entry about user {} language in memory. Looking up in database...'.format(chat_id))
        query = 'SELECT lang FROM user_lang_table WHERE chat_id={}'.format(chat_id)
        row = cursor.execute(query)
        if row:
            lang = cursor.fetchone()[0]
            log.debug('Language of user {} is {}. Was found in database.'.format(chat_id, lang))
            user_lang[chat_id] = lang
        else:
            log.debug('There is no entry about user {} language whatsoever.'.format(chat_id))
            log.debug('Storing entry about user {} language in database and in memory...'.format(chat_id))
            lang = message.from_user.language_code
            log.debug('User {} agent language is '.format(chat_id, lang))
            lang = 'en-US' if not lang.startswith('ru') or not lang.startswith('en') else lang
            log.debug('User {} default language for bot is set to be {}.'.format(chat_id, lang))
            query = 'INSERT INTO user_lang_table (chat_id, lang) VALUES ({}, "{}")'.format(chat_id, lang)
            cursor.execute(query)
            db.commit()
            user_lang[chat_id] = lang
            log.debug('Language of user {} is {}. Was stored in memory and database.'.format(chat_id, lang))
    else:
        log.debug('Language for user {} is {}. Was found in memory.'.format(chat_id, lang))

    log.debug('################ end of user language debug info ################\n')
    return lang


def change_user_language(message):
    curr_lang = get_user_lang(message)
    new_lang = 'ru-RU' if curr_lang == 'en-US' else 'en-US'
    log.debug('Changing user {} language from {} to {}...'.format(message.chat.id, curr_lang, new_lang))
    try:
        set_user_language(message.chat.id, new_lang)
        return True
    except:
        return False


@bot.message_handler(commands=['start'])
def main_menu(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.row('Русский/English')
    markup.row('Самые популярные смартфоны/камеры пользователей @photogpsbot')
    markup.row('Самые популярные объективы пользователей @photogpsbot')
    bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['menu_header'], reply_markup=markup)


@bot.message_handler(commands=[config.abort])
def turn_bot_off(message):
    db_connector.disconnect()
    log.info('Please wait for a sec, bot is turning off...')
    bot.stop_polling()
    log.info('Auf Wiedersehen! Bot is turned off.')
    exit()


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def answer_text_message(message):
    # keyboard_hider = telebot.types.ReplyKeyboardRemove()
    if message.text == 'Русский/English':
        if change_user_language(message):
            bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['switch_lang_success'])
        else:
            bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['switch_lang_failure'])

        # bot.send_message(message.chat.id, text='Вы выбрали русский язык.', reply_markup=keyboard_hider)
    # elif message.text == 'English':
    #     lang = language_pack.language_en
    #     bot.send_message(message.chat.id, text='You chose English.', reply_markup=keyboard_hider)
    #


@bot.message_handler(content_types=['photo'])
def answer_photo_message(message):
    bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['as_file'])
    log_message = ('Name: {} Last name: {} Nickname: {} ID: {} sent '
                   'photo as a photo.'.format(message.from_user.first_name,
                                              message.from_user.last_name,
                                              message.from_user.username,
                                              message.from_user.id))

    log.info(log_message)


def dedupe_string(string):
    splitted_string = string.split(' ')
    deduped_string = ''
    for x in splitted_string:
        if x not in deduped_string:
            deduped_string += x + ' '
    return deduped_string.rstrip()


def exif_to_dd(data, message):
    # Convert exif gps to format that accepts Telegram (and Google Maps for example)

    try:
        # lat, lon = exif_to_dd(raw_coordinates)
        lat_ref = str(data['GPS GPSLatitudeRef'])
        lat = data['GPS GPSLatitude']
        lon_ref = str(data['GPS GPSLongitudeRef'])
        lon = data['GPS GPSLongitude']
    except KeyError:
        log.info('This picture doesn\'t contain coordinates.')
        return [lang_msgs[get_user_lang(message)]['no_gps']]
        # TODO Save exif of photo if converter catch an error trying to convert gps data

    # convert ifdtag from exifread module to decimal degree format of coordinate
    def idf_tag_to_coordinate(tag):

        tag = str(tag).replace('[', '').replace(']', '').split(',')
        if '/' in tag[2]:
            # Slit string like '4444/5555' and divide first one by second one
            tag[2] = int(tag[2].split('/')[0]) / int(tag[2].split('/')[1])
        elif '/' not in tag[2]:
            # Rare case so far - when there is just a number
            tag[2] = int(tag[2])
        else:
            log.warning('Can\'t read gps from file!')
            return False

        return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600

    # Return positive ir negative longitude/latitude from exifread's ifdtag
    lat = -(idf_tag_to_coordinate(lat)) if lat_ref == 'S' else idf_tag_to_coordinate(lat)
    lon = -(idf_tag_to_coordinate(lon)) if lon_ref == 'W' else idf_tag_to_coordinate(lon)
    if lat is False or lon is False:
        return [lang_msgs[get_user_lang(message)]['bad_gps']]
    else:
        return [lat, lon]


def check_camera_tags(tags):

    checked_tags = []

    for tag in tags:
        if tag:  # if there was this information inside EXIF of the photo
            tag = str(tag).strip()
            log.info('Looking up collation for {}'.format(tag))

            # Collate with special table if there more appropriate name for the tag
            # For example instead of just Nikon there can be NIKON CORPORATION in EXIF
            try:
                query = 'SELECT right_tag FROM tag_table WHERE wrong_tag="{}"'.format(tag)
                row = cursor.execute(query)
                if row:
                    tag = cursor.fetchone()[0]  # Get appropriate tag from the table
                    log.debug('Tag after looking up in tag_tables - {}.'.format(tag))
            except (MySQLdb.Error, MySQLdb.Warning) as e:
                log.error(e)

        checked_tags.append(tag)

    return checked_tags


# Save camera info to database to collect statistics
def save_camera_info(data):
    global db

    tables = ['camera_name_table', 'lens_name_table']
    columns = ['camera_name', 'lens_name']

    log.debug('############# debug info about storing exif to db ################')
    for tag, table, column in zip(data, tables, columns):

        if tag:
            log.debug('Name: {}; Table: {}; Column: {} from EXIF'.format(tag, table, column))
            while True:
                try:
                    query = 'SELECT id FROM {} WHERE {} = "{}"'.format(table, column, tag)
                    row = cursor.execute(query)
                    break
                except (MySQLdb.Error, MySQLdb.Warning) as e:
                    log.console(e)
                    return

            if not row:
                try:
                    query = ('INSERT INTO {} ({}, occurrences)'
                             'VALUES ("{}", 1);'.format(table, column, tag))
                    cursor.execute(query)
                    db.commit()
                    log.info('{} was added to {}'.format(tag, table))
                except (MySQLdb.Error, MySQLdb.Warning) as e:
                    log.error(e)
            else:
                try:
                    log.debug('There is {} in {} already'.format(tag, table))
                    query = 'UPDATE {} SET occurrences = occurrences + 1 WHERE {}="{}"'.format(table, column, tag)
                    cursor.execute(query)
                    db.commit()
                    log.debug('{} in {} was updated'.format(tag, table))
                except (MySQLdb.Error, MySQLdb.Warning) as e:
                    log.error(e)

    log.debug('############## end of debug info about storing exif to db###############\n')


def read_exif(image, message):

    answer = []
    exif = exifread.process_file(image, details=False)
    if len(exif.keys()) < 1:
        log.info('This picture doesn\'t contain EXIF.')
        return False, False

    answer.extend(exif_to_dd(exif, message))

    # Get necessary tags from EXIF data

    date_time = exif.get('EXIF DateTimeOriginal', None)
    camera_brand = str(exif.get('Image Make', ''))
    camera_model = str(exif.get('Image Model', ''))
    lens_brand = str(exif.get('EXIF LensMake', ''))
    lens_model = str(exif.get('EXIF LensModel', ''))

    if not any([date_time, camera_brand, camera_model, lens_brand, lens_model]):
        return False  # Means that there is actually no any data of our interest

    # Make user message about camera from exif
    date_time_str = str(date_time) if date_time is not None else None
    camera = dedupe_string(camera_brand + ' ' + camera_model) if camera_brand + ' ' + camera_model != ' ' else None
    lens = dedupe_string(lens_brand + ' ' + lens_model) if lens_brand + ' ' + lens_model != ' ' else None

    camera, lens = check_camera_tags([camera, lens])
    camera_info = camera, lens

    info_about_shot = ''
    for tag, item in zip(lang_msgs[get_user_lang(message)]['camera_info'], [date_time_str, camera, lens]):
        if item:
            info_about_shot += tag + item + '\n'

    answer.append(info_about_shot)
    return answer, camera_info


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['photo_prcs'])
    log_msg = ('Name: {} Last name: {} Nickname: {} ID: {} sent photo as a file.'.format(message.from_user.first_name,
                                                                                         message.from_user.last_name,
                                                                                         message.from_user.username,
                                                                                         message.from_user.id))

    log.info(log_msg)

    # get image
    file_id = bot.get_file(message.document.file_id)
    # Get temporary link to photo that user has sent to bot
    file_path = file_id.file_path
    # Get photo that got telegram bot from user
    r = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(config.token, file_path))
    user_file = BytesIO(r.content)  # Get file-like object of user's photo

    # Get coordinates
    answer, cam_info = read_exif(user_file, message)
    if not answer:
        bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['no_exif'])
    elif len(answer) == 3:  # Sent location and info back to user
        lat, lon = answer[0], answer[1]
        bot.send_location(message.chat.id, lat, lon, live_period=None)
        bot.send_message(message.chat.id, text=answer[2])
        log_msg = ('Sent location and EXIF data back to Name: {} Last name: {} Nickname: '
                   '{} ID: {}'.format(message.from_user.first_name,
                                      message.from_user.last_name,
                                      message.from_user.username,
                                      message.from_user.id))

        log.info(log_msg)
        save_camera_info(cam_info)
    else:
        bot.send_message(message.chat.id, answer[0] + '\n' + answer[1])
        log_msg = ('Sent only EXIF data back to Name: {} Last name: {} Nickname: '
                   '{} ID: {}'.format(message.from_user.first_name,
                                      message.from_user.last_name,
                                      message.from_user.username,
                                      message.from_user.id))
        log.info(log_msg)
        save_camera_info(cam_info)

# error_counter = 0
# while True:
#     if error_counter == 30:
#         log.error('Emergency stop due to loop of polling exceptions')
#         exit()
#     try:
#         if __name__ == '__main__':
#             bot.polling(none_stop=True)  # Keep bot receiving messages
#     except:
#         log.error('Freaking polling!')
#         error_counter += 1


def telegram_polling():
    try:
        bot.polling(none_stop=True, timeout=60)  # Keep bot receiving messages
    except:
        db_connector.disconnect()
        log.warning('Polling issue\n' + traceback.format_exc())
        bot.stop_polling()
        # telegram_polling()


if __name__ == '__main__':
    telegram_polling()
