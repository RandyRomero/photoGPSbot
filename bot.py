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
from datetime import datetime, timedelta
import time

log.info('Starting photoGPSbot...')
log.info('Cleaning log folder...')
clean_log_folder(20)

bot = telebot.TeleBot(config.token)

# Connect to db
db = db_connector.connect()
if not db:
    log.warning('Can\'t connect to db.')

# ping(True) set to check whether or not the connection to the server is
# working. If it has gone down, an automatic reconnection is
# attempted.
db.ping(True)
cursor = db.cursor()

user_lang = {}


# TODO Make caching for user languages
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
    # log.debug('################ get user language debug info ################')
    chat_id = message.chat.id
    log.info('Defining user {} language...'.format(chat_id))
    # log.debug('Looking up in memory...')
    lang = user_lang.get(chat_id, None)
    if not lang:
        # log.debug('There is no entry about user {} language in memory. Looking up in database...'.format(chat_id))
        query = 'SELECT lang FROM user_lang_table WHERE chat_id={}'.format(chat_id)
        row = cursor.execute(query)
        if row:
            lang = cursor.fetchone()[0]
            # log.debug('Language of user {} is {}. Was found in database.'.format(chat_id, lang))
            user_lang[chat_id] = lang
        else:
            lang = 'en-US'
            log.info('User {} default language for bot is set to be en-US.'.format(chat_id))
            query = 'INSERT INTO user_lang_table (chat_id, lang) VALUES ({}, "{}")'.format(chat_id, lang)
            cursor.execute(query)
            db.commit()
            user_lang[chat_id] = lang

    return lang


def change_user_language(message):
    curr_lang = get_user_lang(message)
    new_lang = 'ru-RU' if curr_lang == 'en-US' else 'en-US'
    log.info('Changing user {} language from {} to {}...'.format(message.chat.id, curr_lang, new_lang))
    try:
        set_user_language(message.chat.id, new_lang)
        return True
    except:
        return False


def turn_bot_off():
    db_connector.disconnect()
    log.info('Please wait for a sec, bot is turning off...')
    bot.stop_polling()
    log.info('Auf Wiedersehen! Bot is turned off.')
    exit()


@bot.message_handler(commands=['start'])
def create_main_keyboard(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.row('Русский/English')
    markup.row(lang_msgs[get_user_lang(message)]['top_cams'])
    markup.row(lang_msgs[get_user_lang(message)]['top_lens'])
    bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['menu_header'], reply_markup=markup)


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def handle_menu_response(message):
    # keyboard_hider = telebot.types.ReplyKeyboardRemove()
    if message.text == 'Русский/English':
        if change_user_language(message):
            bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['switch_lang_success'])
            create_main_keyboard(message)
        else:
            bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['switch_lang_failure'])
            create_main_keyboard(message)

    elif message.text == lang_msgs[get_user_lang(message)]['top_cams']:
        log.info('User {} asked for top cams'.format(message.chat.id))
        bot.send_message(message.chat.id, text=get_most_popular_cams_cached('camera_name', message))
        log.info('Returned to {} list of most popular cams.'.format(message.chat.id))

    elif message.text == lang_msgs[get_user_lang(message)]['top_lens']:
        log.info('User {} asked for top lens'.format(message.chat.id))
        bot.send_message(message.chat.id, text=get_most_popular_lens_cached('lens_name', message))
        log.info('Returned to {} list of most popular cams'.format(message.chat.id))

    elif message.text == config.abort:
        bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['bye'])
        turn_bot_off()
    else:
        log.info('Name: {} Last name: {} Nickname: {} ID: {} sent text message.'.format(message.from_user.first_name,
                                                                                        message.from_user.last_name,
                                                                                        message.from_user.username,
                                                                                        message.from_user.id))

        # Answer to user that bot can't make a conversation with him
        bot.send_message(message.chat.id, lang_msgs[get_user_lang(message)]['dont_speak'])


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


def cache_func(func, cache_time):
    """
    Function that prevent calling any given function more often that once in a cache_time.
    It calls given function, then during next cache_times minute it will return cached result of a given function.
    It should save some time.

    :param func: some expensive function that we don't want to call to often because it can slow down the script
    :param cache_time: minutes how much to wait between real func calling and returning cached result
    :return: wrapper that figure out when to call function and when to return cached result
    """
    when_was_called = None  # initialize datetime object
    result = None

    def function_launcher(*args):
        nonlocal func
        nonlocal result
        nonlocal when_was_called

        # when_was_called is None only first time function if called
        # Than it is needed to figure out how many time is left since given func was called last time
        if not when_was_called or when_was_called + timedelta(minutes=cache_time) < datetime.now():
            when_was_called = datetime.now()
            result = func(*args)
            return result
        else:
            log.debug('Return cached result of {}...'.format(func.__name__))
            time_left = when_was_called + timedelta(minutes=cache_time) - datetime.now()
            log.debug('Time to reevaluate result is {}'.format(time_left))
            return result

    return function_launcher


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
    """
    Function that convert stupid code name of the phone or camera from EXIF to meaningful one by looking a
    collation in a special MySQL table
    For example instead of just Nikon there can be NIKON CORPORATION in EXIF
    :param tags: name of a camera and lens
    :return: list with one or two strings which are name of camera and/or lens. If there is not better name
    for the gadget in database, function just returns name how it is
    """
    checked_tags = []

    for tag in tags:
        if tag:  # if there was this information inside EXIF of the photo
            tag = str(tag).strip()
            log.info('Looking up collation for {}'.format(tag))
            try:
                query = 'SELECT right_tag FROM tag_table WHERE wrong_tag="{}"'.format(tag)
                row = cursor.execute(query)
                if row:
                    tag = cursor.fetchone()[0]  # Get appropriate tag from the table
                    log.info('Tag after looking up in tag_tables - {}.'.format(tag))
            except (MySQLdb.Error, MySQLdb.Warning) as e:
                log.error(e)

        checked_tags.append(tag)
    return checked_tags


def get_most_popular_gadgets(cam_or_lens, message):
    """
    Get most common cameras/lenses from database and make list of them
    :param cam_or_lens: string with column name to choose between cameras and lenses
    :param message: telegram object message
    :return: string which is either list of most common cameras/lenses or user message which states that list is empty
    """

    # Make python list to be string list with indexes and new line characters
    def list_to_ordered_str_list(list_of_gadgets):
        string_roaster = ''
        index = 1
        for gadget in list_of_gadgets:
            string_roaster += '{}. {}\n'.format(index, gadget)
            index += 1
        return string_roaster

    log.debug('Evaluating most popular gadgets...')
    all_last_month_gadgets = {}
    month_ago = datetime.strftime(datetime.now() - timedelta(30), '%Y-%m-%d %H:%M:%S')
    query = 'SELECT {} FROM photo_queries_table WHERE time > "{}"'.format(cam_or_lens, month_ago)
    rows = cursor.execute(query)
    if not rows:
        return lang_msgs[get_user_lang(message)]['no_top']
    # Make dictionary to count how may occurrences of each camera or lens we have in our database table
    while True:
        try:
            item = cursor.fetchone()[0]
            if item == 'None':  # Skip empty cells
                continue
            all_last_month_gadgets[item] = 1 if item not in all_last_month_gadgets else all_last_month_gadgets[item] + 1
        except TypeError:  # If there is nothing to catch from cursor anymore
            # Sort dictionary keys by values
            most_popular_gadgets = sorted(all_last_month_gadgets, key=lambda x: all_last_month_gadgets[x], reverse=True)
            len_most_popular_gadgets = len(most_popular_gadgets)
            log.info('There are {} gadgets in database since {}'.format(len_most_popular_gadgets, month_ago))
            if len_most_popular_gadgets > 30:
                return list_to_ordered_str_list(most_popular_gadgets[:30])
            else:
                return list_to_ordered_str_list(most_popular_gadgets)


# Make closures
get_most_popular_cams_cached = cache_func(get_most_popular_gadgets, 5)
get_most_popular_lens_cached = cache_func(get_most_popular_gadgets, 5)


# TODO Make function that returns how many other users have the same camera/smartphone/lens
def get_number_users_by_gadget_name(gadgets, message):
    log.debug('Check how many users also have this camera and lens...')
    log.debug(gadgets)
    answer = ''
    gadget_types = 'camera_name', 'lens_name'
    for gadget_type, gadget in zip(gadget_types, gadgets):
        if not gadget:
            continue
        query = 'SELECT DISTINCT chat_id FROM photo_queries_table WHERE {}="{}"'.format(gadget_type, gadget)
        log.debug(query)
        row = cursor.execute(query)
        log.debug('row: ' + str(row))
        if not row:
            continue
        if gadget_type == 'camera_name':
            answer += lang_msgs[get_user_lang(message)]['camera_users'] + str(row) + '.\n'
        elif gadget_type == 'lens_name':
            answer += lang_msgs[get_user_lang(message)]['lens_users'] + str(row) + '.'

    log.debug('Answer: ' + answer)
    return answer


# Save camera info to database to collect statistics
def save_camera_info(data, message):
    global db
    camera_name, lens_name = data
    chat_id = message.chat.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    username = message.from_user.username

    if camera_name:
        try:
            log.info('Adding new entry to photo_queries_table...')
            query = ('INSERT INTO photo_queries_table (chat_id, camera_name, lens_name, first_name, last_name,'
                     ' username)VALUES ({}, "{}", "{}", "{}", "{}", "{}")'.format(chat_id, camera_name, lens_name,
                                                                                  first_name, last_name, username))
            cursor.execute(query)
            db.commit()
        except (MySQLdb.Error, MySQLdb.Warning) as e:
            log.error(e)
            return


def read_exif(image, message):
    answer = []
    exif = exifread.process_file(image, details=False)
    if len(exif.keys()) < 1:
        log.info('This picture doesn\'t contain EXIF.')
        return False, False

    # Convert EXIF data about location to decimal degrees
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
    others_with_this_gadget = get_number_users_by_gadget_name([camera, lens], message)
    camera_info = camera, lens

    info_about_shot = ''
    for tag, item in zip(lang_msgs[get_user_lang(message)]['camera_info'], [date_time_str, camera, lens]):
        if item:
            info_about_shot += tag + item + '\n'

    info_about_shot += others_with_this_gadget if others_with_this_gadget else ''
    answer.append(info_about_shot)
    return answer, camera_info


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    bot.reply_to(message, lang_msgs[get_user_lang(message)]['photo_prcs'])
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
        bot.reply_to(message, lang_msgs[get_user_lang(message)]['no_exif'])
    elif len(answer) == 3:  # Sent location and info back to user
        lat, lon = answer[0], answer[1]
        bot.send_location(message.chat.id, lat, lon, live_period=None)
        bot.reply_to(message, text=answer[2])
        log_msg = ('Sent location and EXIF data back to Name: {} Last name: {} Nickname: '
                   '{} ID: {}'.format(message.from_user.first_name,
                                      message.from_user.last_name,
                                      message.from_user.username,
                                      message.from_user.id))

        log.info(log_msg)
        save_camera_info(cam_info, message)
    else:
        bot.reply_to(message, answer[0] + '\n' + answer[1])
        log_msg = ('Sent only EXIF data back to Name: {} Last name: {} Nickname: '
                   '{} ID: {}'.format(message.from_user.first_name,
                                      message.from_user.last_name,
                                      message.from_user.username,
                                      message.from_user.id))
        log.info(log_msg)
        save_camera_info(cam_info, message)


# If bot crashes, try to restart and send me a message
def telegram_polling(state):
    try:
        bot.polling(none_stop=True, timeout=90)  # Keep bot receiving messages
        if state == 'recovering':
            bot.send_message(config.me, text='Bot has restarted after critical error.')
    except:
        # db_connector.disconnect()
        # log.warning('Bot crashed with:\n' + traceback.format_exc())
        bot.stop_polling()
        time.sleep(5)
        telegram_polling('recovering')


if __name__ == '__main__':
    telegram_polling('OK')
