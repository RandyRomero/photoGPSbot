"""
Small bot for Telegram that receives your photo and returns you map where
it was taken.
Written by Aleksandr Mikheev.
https://github.com/RandyRomero/photogpsbot
"""

# todo fix formatting in some log calls
# todo refactor code to use if the name == main
# todo check what is wrong with geopy on
#  last versions (some deprecation warning)

import os
import sys
import time
import json
from io import BytesIO
import traceback
from datetime import datetime, timedelta
import socket

# goes as pyTelegramBotAPI in requirements
import telebot
# goes as mysqlclient in requirements
import MySQLdb
from telebot import types
from telebot import apihelper
import exifread
import requests
from geopy.geocoders import Nominatim

from photogpsbot import log, custom_logging
import config
from photogpsbot.db_connector import DB

db = DB()
custom_logging.clean_log_folder(3)

# Load file with messages for user in two languages
with open('photogpsbot/language_pack.txt', 'r', encoding='utf8') as json_file:
    messages = json.load(json_file)

bot = telebot.TeleBot(config.TELEGRAM_TOKEN)
if not socket.gethostname() == config.PROD_HOST_NAME:
    log.info('Working through proxy.')
    apihelper.proxy = {'https': config.PROXY_CONFIG}


# Dictionary that contains user_id -- preferred language for every active user
user_lang = {}


def execute_query(query):
    """
    Tries to execute query. If it is not successful, log about it and send
    a messages directly to my own Telegram account
    :param query: sql query to execute
    :return: cursor object if successful, none if fails
    """
    try:
        return db.execute_query(query)
    except MySQLdb.Error:
        log.error(traceback.format_exc())
        bot.send_message(config.MY_TELEGRAM, text=traceback.format_exc())


def load_last_user_languages(max_users):
    """
    Function that caches preferred language of last active users from database
    to pc memory
    :param max_users: number of entries to be cached
    :return: True if it completed work without errors, False otherwise
    """

    global user_lang
    log.debug('Caching users\' languages from DB...')

    # Select id of last active users
    query = ("SELECT chat_id "
             "FROM photo_queries_table "
             "GROUP BY chat_id "
             "ORDER BY MAX(time) "
             "DESC LIMIT {};".format(max_users))

    log.info('Figure out last active users...')
    cursor = execute_query(query)
    if not cursor:
        log.error("Can't figure out last active users! Check logs")
        return
    if not cursor.rowcount:
        log.warning('There are no users in the db')
        return

    last_active_users_tuple_of_tuples = cursor.fetchall()
    # Make list out of tuple of tuples that is returned by MySQL
    last_active_users = [chat_id[0] for chat_id in
                         last_active_users_tuple_of_tuples]

    log.debug('Caching language preferences for %d '
              'last active users from database...', max_users)
    # Select from db with language preferences of users who
    # were active recently
    query = ("SELECT chat_id, lang "
             "FROM user_lang_table "
             "WHERE chat_id in {};".format(tuple(last_active_users)))

    cursor = execute_query(query)
    if not cursor:
        log.error("Can't Caching language preferences for last active "
                  "users from the db")
        return
    if not cursor.rowcount:
        log.warning('There are no users in the db')
        return

    languages_of_users = cursor.fetchall()
    for line in languages_of_users:
        log.debug('chat_id: {}, language: {}'.format(line[0], line[1]))
        user_lang[line[0]] = line[1]
    log.info('Users languages were cached.')


def clean_old_user_languages_from_memory(max_users):
    # Function to clean RAM from language preferences of users
    # who used a bot a long time ago

    global user_lang

    # Select users that the least active recently
    user_ids = tuple(user_lang.keys())
    query = ('SELECT chat_id '
             'FROM photo_queries_table '
             'WHERE chat_id in {} '
             'GROUP BY chat_id '
             'ORDER BY MAX(time) '
             'LIMIT {}'.format(user_ids, max_users))

    log.info('Figuring out the least active users...')
    cursor = execute_query(query)
    if not cursor:
        log.error("Can't figure out the least active users...")
        return
    if not cursor.rowcount:
        log.warning("There are no users in the db")
        return

    least_active_users_tuple_of_tuples = cursor.fetchall()
    # Make list out of tuple of tuples that is returned by MySQL
    least_active_users = [chat_id[0]
                          for chat_id
                          in least_active_users_tuple_of_tuples]
    log.info('Removing language preferences of %d least '
             'active users from memory...', max_users)
    num_deleted_entries = 0
    for entry in least_active_users:
        log.debug('Deleting {}...'.format(entry))
        deleted_entry = user_lang.pop(entry, None)
        if deleted_entry:
            num_deleted_entries += 1
    log.debug("%d entries with users language preferences "
              "were removed from RAM.", num_deleted_entries)
    return


def set_user_language(chat_id, lang):
    # Function to set language for a user

    log.debug('Updating info about user {} '
              'language in memory & database...'.format(chat_id))
    query = ('UPDATE user_lang_table '
             'SET lang="{}" '
             'WHERE chat_id={}'.format(lang, chat_id))
    db.execute_query(query)
    db.conn.commit()
    user_lang[chat_id] = lang

    # Actually we can set length to be much more,
    # but now I don't have a lot of users, but need to keep an eye whether
    # this function works well or not
    if len(user_lang) > 10:
        clean_old_user_languages_from_memory(2)

    log.info('User %s language was switched to %s', chat_id, lang)


def get_user_lang(chat_id):
    """
    Function to look up user language in dictionary
    (which is like cache), then in database (if it is not in dict).
    If there is not language preference for that user, set en-US by default.

    :param chat_id: user_id
    :return: language tag like ru-RU, en-US as a string
    """
    # log.debug('Defining user %s language...', chat_id)
    lang = user_lang.get(chat_id, None)
    if not lang:
        query = ('SELECT lang '
                 'FROM user_lang_table '
                 'WHERE chat_id={}'.format(chat_id))

        cursor = execute_query(query)
        if not cursor:
            error_message = (
                f"Can't get language of user with id {chat_id} because of "
                "some database bug. Check db_connector logs. Setting user's"
                "language to default - en-US")

            log.error(error_message)
            bot.send_message(chat_id=config.MY_TELEGRAM, text=error_message)
            lang = 'en-US'
            user_lang[chat_id] = lang
            return lang

        # There is no language tag for this user in the database which means
        # this user is here for the first time
        elif not cursor.rowcount:
            lang = 'en-US'
            bot.send_message(config.MY_TELEGRAM, text='You have a new user!')
            log.info('User %s default language for bot is set '
                     'to be en-US.', chat_id)
            query = ('INSERT INTO user_lang_table (chat_id, lang) '
                     'VALUES ({}, "{}")'.format(chat_id, lang))
            db.execute_query(query)
            db.conn.commit()
            user_lang[chat_id] = lang
            return lang

        lang = cursor.fetchone()[0]
        user_lang[chat_id] = lang

        if len(user_lang) > 10:
            clean_old_user_languages_from_memory(2)

    return lang


def change_user_language(chat_id, curr_lang):
    # Switch language from Russian to English or conversely
    new_lang = 'ru-RU' if curr_lang == 'en-US' else 'en-US'
    log.info('Changing user %s language from %s to %s...', chat_id,
             curr_lang, new_lang)
    try:
        set_user_language(chat_id, new_lang)
        return new_lang
    except Exception:
        log.error(traceback.format_exc())
        bot.send_message(config.MY_TELEGRAM, text=traceback.format_exc())
        return False


def get_admin_stat(command):
    # Function that returns statistics to admin by command
    global start_time  # todo get rid of this global
    error_answer = "Can't execute your command. Check logs for error"
    answer = 'There is some statistics for you: \n'

    # Set to a beginning of the day
    today = (datetime
             .today()
             .replace(hour=0, minute=0, second=0, microsecond=0)
             .strftime('%Y-%m-%d %H:%M:%S'))

    # Last users with date of last time when they used bot
    if command == 'last active users':
        log.info('Evaluating last active users with date of '
                 'last time when they used bot...')
        query = ('SELECT MAX(time), last_name, first_name, username '
                 'FROM photo_queries_table '
                 'GROUP BY chat_id, last_name, first_name, username '
                 'ORDER BY MAX(time) '
                 'DESC LIMIT 100')
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        user_roster = cursor.fetchall()
        users = ''
        for user in user_roster:
            for item in user:
                users += '{} '.format(item)
            users += '\n'
        answer += 'Up to 100 last active users by the time ' \
                  'when they sent picture last time:\n'
        answer += users
        log.info('Done.')
        return answer

    elif command == 'total number photos sent':
        log.info('Evaluating total number of photo queries in database...')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table')
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += '{} times users sent photos.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table '
                 'WHERE chat_id !={}'.format(config.MY_TELEGRAM))
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'photos today':
        # Show how many photos have been sent since 00:00:00 of today
        log.info('Evaluating number of photos which were sent today.')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}"'.format(today))
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += f'{cursor.fetchone()[0]} times users sent photos today.'
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}" '
                 'AND chat_id !={}'.format(today, config.MY_TELEGRAM))
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'number of users':
        # Show number of users who has used bot at least
        # once or more (first for the whole time, then today)
        log.info('Evaluating number of users that use bot '
                 'since the first day and today...')
        query = ('SELECT COUNT(DISTINCT chat_id) '
                 'FROM photo_queries_table')
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += 'There are totally {} users.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(DISTINCT chat_id) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}"'.format(today))
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += f'\n{cursor.fetchone()[0]} users have sent photos today.'
        log.info('Done.')
        return answer

    elif command == 'number of gadgets':
        # To show you number smartphones + cameras in database
        log.info('Evaluating number of cameras and smartphones in database...')
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table')
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += (f'There are totally {cursor.fetchone()[0]} '
                   f'cameras/smartphones.')
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}"'.format(today))
        cursor = execute_query(query)
        if not cursor:
            return error_answer
        answer += (f'\n{cursor.fetchone()[0]} cameras/smartphones '
                   'were used today.')
        log.info('Done.')
        return answer

    elif command == 'uptime':
        fmt = 'Uptime: {} days, {} hours, {} minutes and {} seconds.'
        td = datetime.now() - start_time
        # datetime.timedelta.seconds returns you total number of seconds
        # since given time, so you need to perform
        # a little bit of math to make whole hours, minutes and seconds from it
        # And there isn't any normal way to do it in Python unfortunately
        uptime = fmt.format(td.days, td.seconds // 3600, td.seconds % 3600 //
                            60, td.seconds % 60)
        log.info(uptime)
        return uptime


def turn_bot_off():
    # Safely turn the bot off
    bot.send_message(chat_id=config.MY_TELEGRAM,
                     text=messages[get_user_lang(config.MY_TELEGRAM)]['bye'])
    if db.disconnect():
        log.info('Please wait for a sec, bot is turning off...')
        bot.stop_polling()
        log.info('Auf Wiedersehen! Bot is turned off.')
        sys.exit()
    else:
        log.error('Cannot stop bot.')
        bot.send_message(chat_id=config.MY_TELEGRAM, text='Cannot stop bot.')


@bot.message_handler(commands=['start'])
def create_main_keyboard(message):
    chat_id = message.chat.id
    current_user_lang = get_user_lang(chat_id)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True,
                                       resize_keyboard=True)
    markup.row('Русский/English')
    markup.row(messages[current_user_lang]['top_cams'])
    markup.row(messages[current_user_lang]['top_lens'])
    markup.row(messages[current_user_lang]['top_countries'])
    bot.send_message(chat_id, messages[current_user_lang]['menu_header'],
                     reply_markup=markup)


# Decorator to handle text messages
@bot.message_handler(content_types=['text'])
def handle_menu_response(message):
    # keyboard_hider = telebot.types.ReplyKeyboardRemove()
    chat_id = message.chat.id
    current_user_lang = get_user_lang(chat_id)

    if message.text == 'Русский/English':

        current_user_lang = change_user_language(chat_id, current_user_lang)
        if current_user_lang:
            bot.send_message(chat_id, messages[current_user_lang]
                                              ['switch_lang_success'])
            create_main_keyboard(message)
        else:
            bot.send_message(chat_id, messages[get_user_lang(chat_id)]
                                              ['switch_lang_failure'])
            create_main_keyboard(message)

    elif message.text == messages[current_user_lang]['top_cams']:
        log.info('User {} asked for top cams'.format(chat_id))
        bot.send_message(chat_id,
                         text=get_most_popular_items('camera_name', chat_id))
        log.info('List of most popular cameras '
                 'has been returned to %d', chat_id)

    elif message.text == messages[current_user_lang]['top_lens']:
        log.info('User {} asked for top lens'.format(chat_id))
        bot.send_message(chat_id,
                         text=get_most_popular_items('lens_name', chat_id))
        log.info('List of most popular lens has been returned to %d', chat_id)

    elif message.text == messages[current_user_lang]['top_countries']:
        log.info('User {} asked for top countries'.format(chat_id))
        lang_table_name = ('country_ru'
                           if current_user_lang == 'ru-RU'
                           else 'country_en')
        bot.send_message(chat_id,
                         text=get_most_popular_items(lang_table_name, chat_id))
        log.info('List of most popular countries has '
                 'been returned to %d', chat_id)

    elif (message.text.lower() == 'admin' and
          chat_id == int(config.MY_TELEGRAM)):
        # Creates inline keyboard with options for admin Function that handle
        # user interaction with the keyboard called admin_menu

        # Make keyboard object
        keyboard = types.InlineKeyboardMarkup()
        # todo make alias "button = types.InlineKeyboardButton"
        #  to save the space
        keyboard.add(types.InlineKeyboardButton(text='Turn bot off',
                                                callback_data='off'))
        keyboard.add(types.InlineKeyboardButton(text='Last active users',
                                                callback_data='last active'))
        keyboard.add(types.InlineKeyboardButton(text='Total number of photos '
                                                     'were sent',
                                                callback_data='total number '
                                                              'photos sent'))
        keyboard.add(types.InlineKeyboardButton(text='Number of photos today',
                                                callback_data='photos today'))
        keyboard.add(types.InlineKeyboardButton(text='Number of users',
                                                callback_data='number of '
                                                              'users'))
        keyboard.add(types.InlineKeyboardButton(text='Number of gadgets',
                                                callback_data='number '
                                                              'of gadgets'))
        keyboard.add(types.InlineKeyboardButton(text='Uptime',
                                                callback_data='uptime'))
        bot.send_message(config.MY_TELEGRAM,
                         'Admin commands', reply_markup=keyboard)

    else:
        msg = message.from_user
        log.info('Name: %s Last name: %s Nickname: %s ID: %d sent text '
                 'message.', msg.first_name, msg.last_name,
                 msg.username, msg.id)

        # Answer to user that bot can't make a conversation with him
        bot.send_message(chat_id, messages[current_user_lang]['dont_speak'])


@bot.callback_query_handler(func=lambda call: True)
def admin_menu(call):  # Respond commands from admin menu
    # Remove progress bar from pressed button
    bot.answer_callback_query(callback_query_id=call.id, show_alert=False)

    if call.data == 'off':
        turn_bot_off()
    elif call.data == 'last active':
        bot.send_message(config.MY_TELEGRAM,
                         text=get_admin_stat('last active users'))
    elif call.data == 'total number photos sent':
        bot.send_message(config.MY_TELEGRAM,
                         text=get_admin_stat('total number photos sent'))
    elif call.data == 'photos today':
        bot.send_message(config.MY_TELEGRAM,
                         text=get_admin_stat('photos today'))
    elif call.data == 'number of users':
        bot.send_message(config.MY_TELEGRAM,
                         text=get_admin_stat('number of users'))
    elif call.data == 'number of gadgets':
        bot.send_message(config.MY_TELEGRAM,
                         text=get_admin_stat('number of gadgets'))
    elif call.data == 'uptime':
        bot.send_message(config.MY_TELEGRAM,
                         text=get_admin_stat('uptime'))


@bot.message_handler(content_types=['photo'])
def answer_photo_message(message):
    bot.send_message(message.chat.id,
                     messages[get_user_lang(message.chat.id)]['as_file'])
    msg = message.from_user
    log_message = ('Name: %s Last name: %s Nickname: %s ID: %d sent '
                   'photo as a photo.', msg.first_name, msg.last_name,
                   msg.username, msg.id)
    log.info(log_message)


def dedupe_string(string):
    splitted_string = string.split(' ')
    deduped_string = ''
    for x in splitted_string:
        if x not in deduped_string:
            deduped_string += x + ' '
    return deduped_string.rstrip()


def cache_number_users_with_same_feature(func):
    # Closure to cache previous results of given
    # function so to not call database to much
    # It saves result in a dictionary because result depends on a user.
    # cache_time - time in minutes when will
    # be returned cached result instead of calling database

    when_was_called = None
    result = {}

    def func_launcher(feature_name, device_type, chat_id):
        nonlocal func
        nonlocal result
        nonlocal when_was_called
        cache_time = 5

        # Make id in order to cache and return
        # result by feature_type and language of user
        result_id = '{}_{}'.format(feature_name, get_user_lang(chat_id))

        # It's high time to reevaluate result instead
        # of just looking up in cache if countdown went off, if
        # function has not been called yet, if result for
        # feature (like camera, lens or country) not in cache
        high_time = (when_was_called + timedelta(minutes=cache_time) <
                     datetime.now() if when_was_called else True)

        if not when_was_called or high_time or result_id not in result:
            when_was_called = datetime.now()
            result[result_id] = func(feature_name, device_type, chat_id)
            return result[result_id]
        else:
            log.info('Returning cached result of %s',  func.__name__)
            time_left = (when_was_called + timedelta(minutes=cache_time) -
                         datetime.now())
            log.debug('Time to to reevaluate result of %s is %s',
                      func.__name__, str(time_left)[:-7])
            return result[result_id]

    return func_launcher


def cache_most_popular_items(func):
    """
    Function that prevent calling any given function more often that once in
    a cache_time. It calls given function, then during next cache
    return func_launcher_time it
    will return cached result of a given function. Function call given
    function when: it hasn't been called before; cache_time is passed,
    user ask result in another language.

    :param func: some expensive function that we don't want to call too often
    because it can slow down the script
    :return: wrapper that figure out when to call function and when to
    return cached result
    """
    # store time when given function was called last time
    when_was_called = None
    # dictionary to store result where language of user
    # is key and message for user is a value
    result = {}

    def function_launcher(item_type, chat_id):
        nonlocal func
        nonlocal result
        nonlocal when_was_called
        cache_time = 5

        # Only top countries can be returned in different languages.
        # For the other types of queries it doesn't mean a thing.
        if item_type == 'country_ru' or item_type == 'country_en':
            result_id = get_user_lang(chat_id) + item_type
        else:
            result_id = item_type

        # evaluate boolean whether it is high time to call given function or
        # not
        high_time = (when_was_called + timedelta(minutes=cache_time) <
                     datetime.now() if when_was_called else True)

        if not result.get(result_id, None) or not when_was_called or high_time:
            when_was_called = datetime.now()
            result[result_id] = func(item_type, chat_id)
            return result[result_id]
        else:
            log.debug('Return cached result of %s...', func.__name__)
            time_left = (when_was_called + timedelta(minutes=cache_time) -
                         datetime.now())
            log.debug('Time to reevaluate result of %s is %s',
                      func.__name__, str(time_left)[:-7])
            return result[result_id]

    return function_launcher


def get_address(latitude, longitude, lang):

    """
     # Get address as a string by coordinates from photo that user sent to bot
    :param latitude:
    :param longitude:
    :param lang: preferred user language
    :return: address as a string where photo was taken; name of
    country in English and Russian to keep statistics
    of the most popular countries among users of the bot
    """

    coordinates = "{}, {}".format(latitude, longitude)
    log.debug('Getting address from coordinates %s...', coordinates)
    geolocator = Nominatim()

    try:
        location = geolocator.reverse(coordinates, language=lang)

        # Get name of the country in English and Russian language
        if lang == 'en':
            country_en = location.raw['address']['country']
            second_lang = 'ru'
            location2 = geolocator.reverse(coordinates, language=second_lang)
            location2_raw = location2.raw
            country_ru = location2_raw['address']['country']
        else:
            country_ru = location.raw['address']['country']
            second_lang = 'en'
            location2 = geolocator.reverse(coordinates, language=second_lang)
            location2_raw = location2.raw
            country_en = location2_raw['address']['country']
        return location.address, (country_en, country_ru)
    except Exception:
        log.error('Getting address failed!')
        log.error(traceback.format_exc())
        return False


def get_coordinates_from_exif(data, chat_id):
    """
    # Convert GPS coordinates from format in which they are stored in
    EXIF of photo to format that accepts Telegram (and Google Maps for example)

    :param data: EXIF data extracted from photo
    :param chat_id: user id
    :return: either floats that represents longitude and latitude or
    string with error message dedicated to user
    """

    current_user_lang = get_user_lang(chat_id)

    def idf_tag_to_coordinate(tag):
        # Convert ifdtag from exifread module to decimal degree format
        # of coordinate
        tag = str(tag).replace('[', '').replace(']', '').split(',')
        if '/' in tag[2]:
            # Split string like '4444/5555' and divide first integer
            # by second one
            tag[2] = int(tag[2].split('/')[0]) / int(tag[2].split('/')[1])
        elif '/' not in tag[2]:
            # Rare case so far - when there is just a number, not ratio
            tag[2] = int(tag[2])
        else:
            log.warning('Can\'t read gps from file!')
            return False

        return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600

    try:  # Extract data from EXIF
        lat_ref = str(data['GPS GPSLatitudeRef'])
        raw_lat = data['GPS GPSLatitude']
        lon_ref = str(data['GPS GPSLongitudeRef'])
        raw_lon = data['GPS GPSLongitude']
    except KeyError:
        log.info('This picture doesn\'t contain coordinates.')
        return messages[current_user_lang]['no_gps']

    # Return positive or negative longitude/latitude from exifread's ifdtag
    lat = (-(idf_tag_to_coordinate(raw_lat))
           if lat_ref == 'S' else idf_tag_to_coordinate(raw_lat))
    lon = (-(idf_tag_to_coordinate(raw_lon))
           if lon_ref == 'W' else idf_tag_to_coordinate(raw_lon))

    if lat is False or lon is False:
        log.error('Cannot read coordinates of this photo.')
        raw_coordinates = (f'Latitude reference: {lat_ref} '
                           f'Raw latitude: {raw_lat}. '
                           f'Longitude reference: {lon_ref}. '
                           f'Raw longitude: {raw_lon}.')
        log.info(raw_coordinates)
        bot.send_message(config.MY_TELEGRAM,
                         text=('Cannot read these coordinates: ' +
                               raw_coordinates))
        return messages[current_user_lang]['bad_gps']
    elif lat < 1 and lon < 1:
        log.info('There are zero GPS coordinates in this photo.')
        return messages[current_user_lang]['bad_gps']
    else:
        return lat, lon


def check_camera_tags(tags):
    """
    Function that convert stupid code name of a smartphone or camera
    from EXIF to meaningful one by looking a collation in a special MySQL table
    For example instead of just Nikon there can be NIKON CORPORATION in EXIF

    :param tags: name of a camera and lens from EXIF
    :return: list with one or two strings which are name of
    camera and/or lens. If there is not better name for the gadget
    in database, function just returns name how it is
    """
    checked_tags = []

    for tag in tags:
        if tag:  # If there was this information inside EXIF of the photo
            tag = str(tag).strip()
            log.info('Looking up collation for %s', tag)
            query = ('SELECT right_tag '
                     'FROM tag_table '
                     'WHERE wrong_tag="{}"'.format(tag))
            cursor = execute_query(query)
            if not cursor:
                log.error("Can't check the tag because of the db error")
                log.warning("Tag will stay as is.")
                continue
            if cursor.rowcount:
                # Get appropriate tag from the table
                tag = cursor.fetchone()[0]
                log.info('Tag after looking up in tag_tables - %s.', tag)

        checked_tags.append(tag)
    return checked_tags


@cache_most_popular_items
def get_most_popular_items(item_type, chat_id):
    """
    Get most common cameras/lenses/countries from database and
    make list of them
    :param item_type: string with column name to choose between cameras,
    lenses and countries
    :param chat_id: id of user derived from telegram object message
    :return: string which is either list of most common
    cameras/lenses/countries or message which states that list is
    empty
    """

    def list_to_ordered_str_list(list_of_gadgets):
        # Make Python list to be string like roster with indexes and
        # new line characters like:
        # 1. Canon 80D
        # 2. iPhone 4S

        string_roaster = ''
        index = 1
        for item in list_of_gadgets:
            if not item[0]:
                continue
            string_roaster += '{}. {}\n'.format(index, item[0])
            index += 1
        return string_roaster

    log.debug('Evaluating most popular things...')

    # This query returns item types in order where the first one item
    # has the highest number of occurrences
    # in a given column
    query = ('SELECT {0} FROM photo_queries_table '
             'GROUP BY {0} '
             'ORDER BY count({0}) '
             'DESC'.format(item_type))
    cursor = execute_query(query)
    if not cursor:
        log.error("Can't evaluate a list of the most popular items")
        return messages[get_user_lang(chat_id)]['no_top']
    if not cursor.rowcount:
        log.warning('There is nothing in the main database table')
        bot.send_message(chat_id=config.MY_TELEGRAM,
                         text='There is nothing in the main database table')
        return messages[get_user_lang(chat_id)]['no_top']

    popular_items = cursor.fetchall()
    if len(popular_items) > 30:
        log.info('Finish evaluating the most popular items')
        return list_to_ordered_str_list(popular_items[:30])
    else:
        log.info('Finish evaluating the most popular items')
        return list_to_ordered_str_list(popular_items)


@cache_number_users_with_same_feature
def get_number_users_by_feature(feature_name, feature_type, chat_id):
    """
    Get number of users that have same smartphone, camera, lens or that
    have been to the same country
    :param feature_name: string which is name of a particular feature e.g.
    camera name or country name
    :param feature_type: string which is name of the column in database
    :param chat_id: integer which is ID of user
    :return: string which is message to user
    """
    log.debug('Check how many users also have feature: %s...', feature_name)
    answer = ''
    query = ('SELECT DISTINCT chat_id '
             'FROM photo_queries_table '
             'WHERE {}="{}"'.format(feature_type, feature_name))
    cursor = execute_query(query)
    if not cursor or not cursor.rowcount:
        return None
    row = cursor.rowcount

    if feature_type == 'camera_name':
        # asterisks for markdown - to make font bold
        answer += '*{}*{}.'.format(messages[get_user_lang(chat_id)]
                                   ['camera_users'], str(row-1))
    elif feature_type == 'lens_name':
        answer += '*{}*{}.'.format(messages[get_user_lang(chat_id)]
                                   ['lens_users'], str(row - 1))
    elif feature_type == 'country_en':
        answer += '*{}*{}.'.format(messages[get_user_lang(chat_id)]
                                   ['photos_from_country'], str(row - 1))

    return answer


def save_user_query_info(data, message, country=None):
    """
    When user send photo as a file to get information, bot also stores
    information about this query in database to keep statistics that can be
    shown to user in different ways. It stores time of query, telegram id
    of a user, his camera and lens which were used for taking photo, his
    first and last name, nickname and country where the photo was taken

    :param data: list with name of camera and lens (if any)
    :param message: Telegram object "message" that contains info about user
    and such
    :param country: country where photo was taken
    :return: None
    """
    camera_name, lens_name = data
    camera_name = ('NULL' if not camera_name
                   else '{0}{1}{0}'.format('"', camera_name))
    lens_name = 'NULL' if not lens_name else '{0}{1}{0}'.format('"', lens_name)
    chat_id = message.chat.id
    msg = message.from_user
    first_name = ('NULL' if not msg.first_name
                  else '{0}{1}{0}'.format('"', msg.first_name))
    last_name = ('NULL' if not msg.last_name
                 else '{0}{1}{0}'.format('"', msg.last_name))
    username = ('NULL' if not msg.username
                else '{0}{1}{0}'.format('"', msg.username))
    if not country:
        country_en = country_ru = 'NULL'
    else:
        country_en = '"{}"'.format(country[0])
        country_ru = '"{}"'.format(country[1])

    log.info('Adding user query to photo_queries_table...')

    query = ('INSERT INTO photo_queries_table '
             '(chat_id, camera_name, lens_name, first_name, last_name, '
             'username, country_en, country_ru) '
             'VALUES ({}, {}, {}, {}, {}, {}, '
             '{}, {})'.format(chat_id, camera_name, lens_name, first_name,
                              last_name, username, country_en,
                              country_ru))

    db.execute_query(query)
    db.conn.commit()
    log.info('User query was successfully added to the database.')
    return


def read_exif(image, message):
    """
    Get various info about photo that user sent: time when picture was taken,
    location as longitude and latitude, post address, type of
    camera/smartphone and lens, how many people have
    the same camera/lens.

    :param image: actual photo that user sent to bot
    :param message: object from Telegram that contains user id, name etc
    :return: list with three values. First value called answer is also list
    that contains different information about picture. First value of answer
    is either tuple with coordinates from photo or string message
    that photo doesn't contain coordinates. Second value of answer is string
    with photo details: time, camera, lens from exif and, if any, messages
    how many other bot users have the same camera/lens.
    Second value in list that this function returns is camera info, which is
    list with one or two items: first is name of the camera/smartphone,
    second, if exists, name of the lens. Third  value in list that this
    function returns is a country where picture was taken.

    """
    chat_id = message.chat.id
    answer = []
    exif = exifread.process_file(image, details=False)
    if not len(exif.keys()):
        log.info('This picture doesn\'t contain EXIF.')
        return False

    # Get info about camera ang lend from EXIF
    date_time = exif.get('EXIF DateTimeOriginal', None)
    camera_brand = str(exif.get('Image Make', ''))
    camera_model = str(exif.get('Image Model', ''))
    lens_brand = str(exif.get('EXIF LensMake', ''))
    lens_model = str(exif.get('EXIF LensModel', ''))

    if not any([date_time, camera_brand, camera_model, lens_brand,
                lens_model]):
        # Means that there is actually no any data of our interest
        return False

    date_time_str = str(date_time) if date_time is not None else None
    # Merge brand and model together and get rid of repetitive words
    camera_string = f'{camera_brand} {camera_model}'
    camera = dedupe_string(camera_string) if camera_string != ' ' else None
    lens_string = f'{lens_brand} {lens_model}'
    lens = dedupe_string(lens_string) if lens_string != ' ' else None

    # Check if there is more appropriate name for camera/lens
    camera, lens = check_camera_tags([camera, lens])
    camera_info = camera, lens

    exif_converter_result = get_coordinates_from_exif(exif, chat_id)
    # If tuple - there are coordinates, else - message to user t
    # hat there are no coordinates
    if isinstance(exif_converter_result, tuple):
        coordinates = exif_converter_result
        answer.append(coordinates)
        lang = 'ru' if get_user_lang(chat_id) == 'ru-RU' else 'en'
        try:
            address, country = get_address(*coordinates, lang)
        except TypeError:
            address, country = '', None
    else:
        # Add user message that photo doesn't have info about location or
        # it can't be read
        address, country = '', None
        user_msg = exif_converter_result
        answer.append(user_msg)

    if country:
        save_user_query_info(camera_info, message, country)
    else:
        save_user_query_info(camera_info, message)

    others_with_this_cam = get_number_users_by_feature(camera,
                                                       'camera_name', chat_id)

    others_with_this_lens = (
        get_number_users_by_feature(lens, 'lens_name', chat_id)
        if lens else None)

    others_from_this_country = (
        get_number_users_by_feature(country[0], 'country_en', chat_id)
        if country else None)

    # Make user message about camera from exif
    info_about_shot = ''
    for tag, item in zip(messages[get_user_lang(chat_id)]['camera_info'],
                         [date_time_str, camera, lens, address]):
        if item:
            info_about_shot += '*{}*: {}\n'.format(tag, item)

    info_about_shot += others_with_this_cam if others_with_this_cam else ''
    info_about_shot += ('\n' + others_with_this_lens
                        if others_with_this_lens else '')
    info_about_shot += ('\n' + others_from_this_country
                        if others_from_this_country else '')
    answer.append(info_about_shot)

    return [answer, camera_info, country]


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    chat_id = message.chat.id
    current_user_lang = get_user_lang(chat_id)
    bot.reply_to(message, messages[current_user_lang]['photo_prcs'])
    msg = message.from_user
    log.info('Name: %s Last name: %s Nickname: %s ID: %d sent photo as a '
             'file.', msg.first_name, msg.last_name, msg.username, msg.id)

    file_id = bot.get_file(message.document.file_id)
    # Get temporary link to a photo that user has sent to bot
    file_path = file_id.file_path
    # Download photo that got telegram bot from user
    if os.path.exists('prod.txt'):
        r = requests.get('https://api.telegram.org/file/bot{0}/{1}'
                         .format(config.TELEGRAM_TOKEN, file_path))
    else:
        r = requests.get('https://api.telegram.org/file/bot{0}/{1}'
                         .format(config.TELEGRAM_TOKEN, file_path),
                         proxies={'https': config.PROXY_CONFIG})

    # Get file-like object of user's photo
    user_file = BytesIO(r.content)

    # Read data from photo and prepare answer for user with location and etc.
    read_exif_result = read_exif(user_file, message)

    # Send message to user that there is no EXIF data in his picture
    if not read_exif_result:
        bot.reply_to(message, messages[current_user_lang]['no_exif'])
        return

    answer, cam_info, country = read_exif_result

    msg = message.from_user

    # Send location and info about shot back to user
    if isinstance(answer[0], tuple):
        lat, lon = answer[0]
        bot.send_location(chat_id, lat, lon, live_period=None)
        bot.reply_to(message, text=answer[1], parse_mode='Markdown')

        log.info('Sent location and EXIF data back to Name: %s Last name: %s '
                 'Nickname: %s ID: %d', msg.first_name, msg.last_name,
                 msg.username, msg.id)
        return

    # Sent to user only info about camera because there is no gps
    # coordinates in his photo
    user_msg = '{}\n{}'.format(answer[0], answer[1])
    bot.reply_to(message, user_msg, parse_mode='Markdown')
    log.info('Sent only EXIF data back to Name: %s Last name: %s '
             'Nickname: %s ID: %d', msg.first_name, msg.last_name,
             msg.username, msg.id)


# I think you can safely cache several hundred or thousand of
# user-lang pairs without consuming to much memory, but for development
# purpose I will set it to some minimum to be sure that
# calling to DB works properly
load_last_user_languages(10)


def start_bot():
    log.info('Starting photogpsbot...')
    bot.polling(none_stop=True, timeout=90)  # Keep bot receiving messages


try:
    start_time = datetime.now()
    start_bot()

except requests.exceptions.ReadTimeout as e:
    log.error(e)
    bot.stop_polling()
    log.warning('Pausing bot for 30 seconds...')
    time.sleep(30)
    log.warning('Try to start the bot again...')
    start_bot()

