#!python3
# -*- coding: utf-8 -*-

# Small bot for Telegram that receive your photo and return you map where it was taken.
# Written by Aleksandr Mikheev.
# https://github.com/RandyRomero/photoGPSbot

import sys
import time
import MySQLdb
import telebot
from telebot import types
import exifread
import requests
from io import BytesIO
import traceback
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
import config
from handle_logs import log, clean_log_folder
from language_pack import lang_msgs
import db_connector


log.info('Starting photoGPSbot...')
clean_log_folder(20)

bot = telebot.TeleBot(config.token)

# Connect to database
db = db_connector.DB()
if not db:
    log.error('Can\'t connect to db.')
    bot.send_message(config.me, text='photoGPSbot can\'t connect to MySQL database!')

user_lang = {}  # Dictionary that contains user_id -- preferred language for every active user


def load_last_user_languages(max_users):
    """
    Function that caches preferred language of last active users from database to pc memory
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
    try:
        cursor = db.execute_query(query)
    except (MySQLdb.Error, MySQLdb.Warning) as err:
        log.warning(err)
        bot.send_message(config.me, text=err)
        return False

    if cursor.rowcount:
        last_active_users_tuple_of_tuples = cursor.fetchall()
        # Make list out of tuple of tuples that is returned by MySQL
        last_active_users = [chat_id[0] for chat_id in last_active_users_tuple_of_tuples]
    else:
        log.warning('There are no last active users')
        return False

    log.debug('Caching language preferences for {} last active users from database...'.format(max_users))
    # Select from db with language preferences of users who were active recently
    query = "SELECT chat_id, lang FROM user_lang_table WHERE chat_id in {};".format(tuple(last_active_users))
    cursor = db.execute_query(query)
    if cursor.rowcount:
        languages_of_users = cursor.fetchall()
        for line in languages_of_users:
            log.debug('chat_id: {}, language: {}'.format(line[0], line[1]))
            user_lang[line[0]] = line[1]
        return True
    else:
        log.warning('There are no entries about user languages in database.')
        return False


def clean_old_user_languages_from_memory(max_users):
    # Function to clean RAM from language preferences of users who used a bot a long time ago

    global user_lang

    # Select users that the least active recently
    user_ids = tuple(user_lang.keys())
    query = ('SELECT chat_id '
             'FROM photo_queries_table '
             'WHERE chat_id in {} '
             'GROUP BY chat_id '
             'ORDER BY MAX(time) '
             'LIMIT {}'.format(user_ids, max_users))

    log.info('Figuring out least active users...')
    try:
        cursor = db.execute_query(query)
    except (MySQLdb.Error, MySQLdb.Warning) as err:
        log.warning(err)
        bot.send_message(config.me, text=err)
        return False

    if cursor.rowcount:
        least_active_users_tuple_of_tuples = cursor.fetchall()
        # Make list out of tuple of tuples that is returned by MySQL
        least_active_users = [chat_id[0] for chat_id in least_active_users_tuple_of_tuples]
    else:
        log.warning('There are no least active users')
        return False

    log.info('Removing language preferences of {} least active users from memory...'.format(max_users))
    num_deleted_entries = 0
    for entry in least_active_users:
        log.debug('Deleting {}...'.format(entry))
        deleted_entry = user_lang.pop(entry, None)
        if deleted_entry:
            num_deleted_entries += 1
    log.debug('{} entries with users language preferences were removed from RAM.'.format(num_deleted_entries))
    return True


def set_user_language(chat_id, lang):
    # Function to set language for a user

    log.debug('Updating info about user {} language in memory & database...'.format(chat_id))
    query = 'UPDATE user_lang_table SET lang="{}" WHERE chat_id={}'.format(lang, chat_id)
    db.execute_query(query)
    db.conn.commit()
    user_lang[chat_id] = lang

    # Actually we can set length to be much more, but now I don't have a lot of users, but need to keep an eye whether
    # this function works well or not
    if len(user_lang) > 10:
        clean_log_folder(2)

    log.info('User {} language was switched to {}'.format(chat_id, lang))


def get_user_lang(chat_id):
    """
    Function to look up user language in dictionary (which is like cache), then in database (if it is not in dict).
    If there is not language preference for that user, set en-US by default.

    :param chat_id: user_id
    :return: language tag like ru-RU, en-US as a string
    """
    log.info('Defining user {} language...'.format(chat_id))
    lang = user_lang.get(chat_id, None)
    if not lang:
        query = 'SELECT lang FROM user_lang_table WHERE chat_id={}'.format(chat_id)
        try:
            cursor = db.execute_query(query)
        except (MySQLdb.Error, MySQLdb.Warning) as err:
            log.warning(err)
            lang = 'en-US'
            user_lang[chat_id] = lang
            return lang

        if cursor.rowcount:
            lang = cursor.fetchone()[0]
            user_lang[chat_id] = lang
        else:
            lang = 'en-US'
            bot.send_message(config.me, text='You have a new user!')
            log.info('User {} default language for bot is set to be en-US.'.format(chat_id))
            query = 'INSERT INTO user_lang_table (chat_id, lang) VALUES ({}, "{}")'.format(chat_id, lang)
            db.execute_query(query)
            db.conn.commit()
            user_lang[chat_id] = lang

        if len(user_lang) > 10:
            clean_log_folder(2)

    return lang


def change_user_language(chat_id, curr_lang):
    # Switch language from Russian to English or conversely
    new_lang = 'ru-RU' if curr_lang == 'en-US' else 'en-US'
    log.info('Changing user {} language from {} to {}...'.format(chat_id, curr_lang, new_lang))
    try:
        set_user_language(chat_id, new_lang)
        return new_lang
    except:  # who knows what god can send us
        log.error(traceback.format_exc())
        bot.send_message(config.me, text=traceback.format_exc())
        return False


def get_admin_stat(command):
    # Function that returns statistics to admin by command
    global start_time
    answer = 'There is some statistics for you: \n'
    # Set to a beginning of the day
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:%M:%S')

    # Last users with date of last time when they used bot
    if command == 'last active users':
        log.info('Evaluating last active users with date of last time when they used bot...')
        query = ('SELECT MAX(time), last_name, first_name, username '
                 'FROM photo_queries_table '
                 'GROUP BY chat_id '
                 'ORDER BY MAX(time) '
                 'DESC LIMIT 100')
        cursor = db.execute_query(query)
        user_roster = cursor.fetchall()
        users = ''
        for user in user_roster:
            for item in user:
                users += '{} '.format(item)
            users += '\n'
        answer += 'Up to 100 last active users by the time when they sent picture last time:\n'
        answer += users
        log.info('Done.')
        return answer

    elif command == 'total number photos sent':
        log.info('Evaluating total number of photo queries in database...')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table')
        cursor = db.execute_query(query)
        answer += '{} times users sent photos.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table '
                 'WHERE chat_id !={}'.format(config.me))
        cursor = db.execute_query(query)
        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'photos today':
        # Show how many photos have been sent since 00:00:00 of today
        log.info('Evaluating number of photos which were sent today.')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}"'.format(today))
        cursor = db.execute_query(query)
        answer += '{} times users sent photos today.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}" '
                 'AND chat_id !={}'.format(today, config.me))
        cursor = db.execute_query(query)
        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'number of users':
        # Show number of users who has used bot at least once or more (first for the whole time, then today)
        log.info('Evaluating number of users that use bot since the first day and today...')
        query = ('SELECT COUNT(DISTINCT chat_id) '
                 'FROM photo_queries_table')
        cursor = db.execute_query(query)
        answer += 'There are totally {} users.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(DISTINCT chat_id) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}"'.format(today))
        cursor = db.execute_query(query)
        answer += '\n{} users have sent photos today.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'number of gadgets':
        # To show you number smartphones + cameras in database
        log.info('Evaluating number of cameras and smartphones in database...')
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table')
        cursor = db.execute_query(query)
        answer += 'There are totally {} cameras/smartphones.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table '
                 'WHERE time > "{}"'.format(today))
        cursor = db.execute_query(query)
        answer += '\n{} cameras/smartphones were used today.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'uptime':
        fmt = 'Uptime: {} days, {} hours, {} minutes and {} seconds.'
        td = datetime.now() - start_time
        # datetime.timedelta.seconds returns you total number of seconds since given time, so you need to perform
        # a little bit of math to make whole hours, minutes and seconds from it
        # And there isn't any normal way to do it in Python unfortunately
        return fmt.format(td.days, td.seconds // 3600, td.seconds % 3600 // 60, td.seconds % 60)


def turn_bot_off():
    # Safely turn bot off
    bot.send_message(config.me, lang_msgs[get_user_lang(config.me)]['bye'])
    if db.disconnect():
        log.info('Please wait for a sec, bot is turning off...')
        bot.stop_polling()
        log.info('Auf Wiedersehen! Bot is turned off.')
        sys.exit()
    else:
        log.error('Cannot stop bot.')


@bot.message_handler(commands=['start'])
def create_main_keyboard(message):
    chat_id = message.chat.id
    current_user_lang = get_user_lang(chat_id)
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.row('Русский/English')
    markup.row(lang_msgs[current_user_lang]['top_cams'])
    markup.row(lang_msgs[current_user_lang]['top_lens'])
    markup.row(lang_msgs[current_user_lang]['top_countries'])
    bot.send_message(chat_id, lang_msgs[current_user_lang]['menu_header'], reply_markup=markup)


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def handle_menu_response(message):
    # keyboard_hider = telebot.types.ReplyKeyboardRemove()
    chat_id = message.chat.id
    current_user_lang = get_user_lang(chat_id)

    if message.text == 'Русский/English':

        current_user_lang = change_user_language(chat_id, current_user_lang)
        if current_user_lang:
            bot.send_message(chat_id, lang_msgs[current_user_lang]['switch_lang_success'])
            create_main_keyboard(message)
        else:
            bot.send_message(chat_id, lang_msgs[get_user_lang(chat_id)]['switch_lang_failure'])
            create_main_keyboard(message)

    elif message.text == lang_msgs[current_user_lang]['top_cams']:
        log.info('User {} asked for top cams'.format(chat_id))
        bot.send_message(chat_id, text=get_most_popular_cams_cached('camera_name', chat_id))
        log.info('List of most popular cameras has been returned to {} '.format(chat_id))

    elif message.text == lang_msgs[current_user_lang]['top_lens']:
        log.info('User {} asked for top lens'.format(chat_id))
        bot.send_message(chat_id, text=get_most_popular_lens_cached('lens_name', chat_id))
        log.info('List of most popular lens has been returned to {} '.format(chat_id))

    elif message.text == lang_msgs[current_user_lang]['top_countries']:
        log.info('User {} asked for top countries'.format(chat_id))
        table_name = 'country_ru' if current_user_lang == 'ru-RU' else 'country_en'
        bot.send_message(chat_id, text=get_most_popular_countries_cached(table_name, chat_id))
        log.info('List of most popular countries has been returned to {} '.format(chat_id))

    elif message.text.lower() == 'admin' and chat_id == config.me:
        # It creates inline keyboard with options for admin
        # Function that handle user interaction with the keyboard called admin_menu
        keyboard = types.InlineKeyboardMarkup()  # Make keyboard object
        keyboard.add(types.InlineKeyboardButton(text='Turn bot off', callback_data='off'))
        keyboard.add(types.InlineKeyboardButton(text='Last active users', callback_data='last active'))
        keyboard.add(types.InlineKeyboardButton(text='Total number of photos were sent',
                                                callback_data='total number photos sent'))
        keyboard.add(types.InlineKeyboardButton(text='Number of photos today', callback_data='photos today'))
        keyboard.add(types.InlineKeyboardButton(text='Number of users', callback_data='number of users'))
        keyboard.add(types.InlineKeyboardButton(text='Number of gadgets', callback_data='number of gadgets'))
        keyboard.add(types.InlineKeyboardButton(text='Uptime', callback_data='uptime'))
        bot.send_message(config.me, 'Admin commands', reply_markup=keyboard)

    else:
        log.info('Name: {} Last name: {} Nickname: {} ID: {} sent text message.'.format(message.from_user.first_name,
                                                                                        message.from_user.last_name,
                                                                                        message.from_user.username,
                                                                                        message.from_user.id))

        # Answer to user that bot can't make a conversation with him
        bot.send_message(chat_id, lang_msgs[current_user_lang]['dont_speak'])


@bot.callback_query_handler(func=lambda call: True)
def admin_menu(call):
    # Respond commands from admin menu
    bot.answer_callback_query(callback_query_id=call.id, show_alert=False)  # Remove progress bar from pressed button

    if call.data == 'off':
        turn_bot_off()
    elif call.data == 'last active':
        bot.send_message(config.me, text=get_admin_stat('last active users'))
    elif call.data == 'total number photos sent':
        bot.send_message(config.me, text=get_admin_stat('total number photos sent'))
    elif call.data == 'photos today':
        bot.send_message(config.me, text=get_admin_stat('photos today'))
    elif call.data == 'number of users':
        bot.send_message(config.me, text=get_admin_stat('number of users'))
    elif call.data == 'number of gadgets':
        bot.send_message(config.me, text=get_admin_stat('number of gadgets'))
    elif call.data == 'uptime':
        bot.send_message(config.me, text=get_admin_stat('uptime'))


@bot.message_handler(content_types=['photo'])
def answer_photo_message(message):
    bot.send_message(message.chat.id, lang_msgs[get_user_lang(message.chat.id)]['as_file'])
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


def cache_number_users_with_same_feature(func, cache_time):
    when_was_called = None
    result = {}

    def func_launcher(feature_name, device_type, chat_id):
        nonlocal func
        nonlocal result
        nonlocal when_was_called

        # Add language tag to feature name to avoid returning to user cached result in another language
        feature_name_with_lang = '{}_{}'.format(feature_name,  get_user_lang(chat_id))

        # It's high time to call reevaluate result instead of just looking up in cache if countdown went off, if
        # function has not been called yet, if result for feature (like camera, lens or country) not in cache
        high_time = when_was_called + timedelta(minutes=cache_time) < datetime.now() if when_was_called else True
        if not when_was_called or high_time or feature_name_with_lang not in result:
            when_was_called = datetime.now()

            result[feature_name_with_lang] = func(feature_name, device_type, chat_id)
            return result[feature_name_with_lang]
        else:
            log.info('Returning cached result of ' + func.__name__)
            time_left = when_was_called + timedelta(minutes=cache_time) - datetime.now()
            log.debug('Time to reevaluate result of {} is {}'.format(func.__name__, time_left))
            return result[feature_name_with_lang]

    return func_launcher


def cache_most_popular_items(func, cache_time):
    """
    Function that prevent calling any given function more often that once in a cache_time.
    It calls given function, then during next cache_time  it will return cached result of a given function.
    Function call given function when: it hasn't been called before; cache_time is passed, user ask result in
    another language.

    :param func: some expensive function that we don't want to call too often because it can slow down the script
    :param cache_time: minutes how much to wait between real func calling and returning cached result
    :return: wrapper that figure out when to call function and when to return cached result
    """
    when_was_called = None  # store time when given function was called last time
    result = {}  # dictionary to store result where language of user is key and message for user is a value

    def function_launcher(item_type, chat_id):
        nonlocal func
        nonlocal result
        nonlocal when_was_called
        lang = get_user_lang(chat_id)

        # evaluate boolean whether it is high time to call given function or not
        high_time = when_was_called + timedelta(minutes=cache_time) < datetime.now() if when_was_called else True

        if not result.get(lang, None) or not when_was_called or high_time:
            when_was_called = datetime.now()
            result[lang] = func(item_type, chat_id)
            return result[lang]
        else:
            log.debug('Return cached result of {}...'.format(func.__name__))
            time_left = when_was_called + timedelta(minutes=cache_time) - datetime.now()
            log.debug('Time to reevaluate result of {} is {}'.format(func.__name__, time_left))
            return result[lang]

    return function_launcher


def get_address(latitude, longitude, lang):
    # start_time = datetime.now()
    # Get address as a string by coordinates from photo that user sent to bot

    coordinates = "{}, {}".format(latitude, longitude)
    log.info('Getting address from coordinates {}...'.format(coordinates))
    geolocator = Nominatim()

    try:
        location = geolocator.reverse(coordinates, language=lang)
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
        # log.debug("It took {} seconds for get_address function to do the job".format((datetime.now() -
        #                                                                               start_time).seconds))
        return location.address, (country_en, country_ru)
    except:
        log.error('Getting address failed!')
        log.error(traceback.format_exc())
        return False


# Convert exif gps to format that accepts Telegram (and Google Maps for example)
def get_coordinates_from_exif(data, chat_id):
    current_user_lang = get_user_lang(chat_id)

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

    try:
        # lat, lon = exif_to_dd(raw_coordinates)
        lat_ref = str(data['GPS GPSLatitudeRef'])
        raw_lat = data['GPS GPSLatitude']
        lon_ref = str(data['GPS GPSLongitudeRef'])
        raw_lon = data['GPS GPSLongitude']
    except KeyError:
        log.info('This picture doesn\'t contain coordinates.')
        return lang_msgs[current_user_lang]['no_gps']

    # Return positive or negative longitude/latitude from exifread's ifdtag
    lat = -(idf_tag_to_coordinate(raw_lat)) if lat_ref == 'S' else idf_tag_to_coordinate(raw_lat)
    lon = -(idf_tag_to_coordinate(raw_lon)) if lon_ref == 'W' else idf_tag_to_coordinate(raw_lon)
    if lat is False or lon is False:
        log.error('Cannot read coordinates of this photo.')
        raw_coordinates = ('Latitude reference: {}\n.Raw latitude: {}\n.Longitude reference: {}\n.'
                           'Raw longitude: {}.'.format(lat_ref, raw_lat, lon_ref, raw_lon))
        log.info(raw_coordinates)
        bot.send_message(config.me, text=('Cannot read these coordinates: ' + raw_coordinates))
        return lang_msgs[current_user_lang]['bad_gps']
    elif lat < 1 and lon < 1:
        log.info('There are zero GPS coordinates in this photo.')
        return lang_msgs[current_user_lang]['bad_gps']

    else:
        return lat, lon


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
                cursor = db.execute_query(query)
                if cursor.rowcount:
                    tag = cursor.fetchone()[0]  # Get appropriate tag from the table
                    log.info('Tag after looking up in tag_tables - {}.'.format(tag))
            except (MySQLdb.Error, MySQLdb.Warning) as e:
                log.error(e)

        checked_tags.append(tag)
    return checked_tags


def get_most_popular_items(item_type, chat_id):
    """
    Get most common cameras/lenses from database and make list of them
    :param item_type: string with column name to choose between cameras, lenses and countries
    :param chat_id: id of user derived from telegram object message
    :return: string which is either list of most common cameras/lenses/countries or message which states that list is
    empty
    """

    # Make python list to be string roster with indexes and new line characters like:
    # 1. Canon 80D
    # 2. iPhone 4S
    def list_to_ordered_str_list(list_of_gadgets):
        string_roaster = ''
        index = 1
        for item in list_of_gadgets:
            if not item[0]:
                continue
            string_roaster += '{}. {}\n'.format(index, item[0])
            index += 1
        return string_roaster

    log.debug('Evaluating most popular gadgets...')
    month_ago = datetime.strftime(datetime.now() - timedelta(30), '%Y-%m-%d %H:%M:%S')

    # This query returns item types in order where the first one item has the highest number of occurrences
    # in a given column
    query = ('SELECT {0} FROM photo_queries_table WHERE time > "{1}" GROUP BY {0} '
             'ORDER BY count({0}) DESC'.format(item_type, month_ago))
    try:
        cursor = db.execute_query(query)
        if not cursor.rowcount:
            log.info('Can\'t evaluate a list of the most popular items')
            return lang_msgs[get_user_lang(chat_id)]['no_top']

        popular_items = cursor.fetchall()
        if len(popular_items) > 30:
            log.info('Finish evaluating the most popular items')
            return list_to_ordered_str_list(popular_items[:30])
        else:
            log.info('Finish evaluating the most popular items')
            return list_to_ordered_str_list(popular_items)
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        log.error(e)


# Make closures
get_most_popular_cams_cached = cache_most_popular_items(get_most_popular_items, 5)
get_most_popular_lens_cached = cache_most_popular_items(get_most_popular_items, 5)
get_most_popular_countries_cached = cache_most_popular_items(get_most_popular_items, 5)


def get_number_users_by_feature(feature_name, feature_type, chat_id):
    """
    Get number of users that have same smartphone, camera, lens ir that have been to the same country
    :param feature_name: string which is name of particular feature e.g. camera name our country name
    :param feature_type: string which is basically name of the column in database
    :param chat_id: integer which is ID of user
    :return: string which is message to user
    """
    log.debug('Check how many users also have feature: {}...'.format(feature_name))
    answer = ''
    query = 'SELECT DISTINCT chat_id FROM photo_queries_table WHERE {}="{}"'.format(feature_type, feature_name)
    cursor = db.execute_query(query)
    # Because 1 is yourself (but sometimes you can use it for debug
    row = cursor.rowcount
    if not row or row < 1:
        return None
    if feature_type == 'camera_name':
        # asterisks for markdown - to make font bold
        answer += '*{}*{}.'.format(lang_msgs[get_user_lang(chat_id)]['camera_users'], str(row-1))
    elif feature_type == 'lens_name':
        answer += '*{}*{}.'.format(lang_msgs[get_user_lang(chat_id)]['lens_users'], str(row - 1))
    elif feature_type == 'country_en':
        answer += '*{}*{}.'.format(lang_msgs[get_user_lang(chat_id)]['photos_from_country'], str(row - 1))

    return answer


# Make closure which preservers result of the function in order not to call database too often
get_number_users_with_same_feature = cache_number_users_with_same_feature(get_number_users_by_feature, 5)


# Save camera info to database to collect statistics
def save_user_query_info(data, message, country=None):
    camera_name, lens_name = data
    camera_name = 'NULL' if not camera_name else '{0}{1}{0}'.format('"', camera_name)
    lens_name = 'NULL' if not lens_name else '{0}{1}{0}'.format('"', lens_name)
    chat_id = message.chat.id
    first_name = 'NULL' if not message.from_user.first_name else '{0}{1}{0}'.format('"', message.from_user.first_name)
    last_name = 'NULL' if not message.from_user.last_name else '{0}{1}{0}'.format('"', message.from_user.last_name)
    username = 'NULL' if not message.from_user.username else '{0}{1}{0}'.format('"', message.from_user.username)
    if not country:
        country_en = country_ru = 'NULL'
    else:
        country_en = '{0}{1}{0}'.format('"', country[0])
        country_ru = '{0}{1}{0}'.format('"', country[1])

    if not camera_name:
        log.warning('Something went wrong. There should be camera name to store it in database but there isn\'t')
        return

    try:
        log.info('Adding new entry to photo_queries_table...')

        query = ('INSERT INTO photo_queries_table '
                 '(chat_id, camera_name, lens_name, first_name, last_name, username, country_en, country_ru) '
                 'VALUES ({}, {}, {}, {}, {}, {}, '
                 '{}, {})'.format(chat_id, camera_name, lens_name, first_name, last_name, username, country_en,
                                  country_ru))

        db.execute_query(query)
        db.conn.commit()
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        log.error(e)
        return


def read_exif(image, message):
    """
    # Get various info about photo that user sent: time when picture was taken, location as longitude and latitude,
    # post address, type of camera/smartphone and lens, how many people have the same camera/lens.

    :param image: actual photo that user sent to bot
    :param message: object from Telegram that contains user id, name etc
    :return: list with three values. First value called answer is also list that contains different information
    about picture. First value of answer is either tuple with coordinates from photo or string message
    that photo doesn't contain coordinates. Second value of answer is string with photo details: time, camera, lens
    from exif and, if any, messages how many other bot users have the same camera/lens.
    Second value in list that this function returns is camera info, which is list with one or two items: first is
    name of the samera/smartphone, second, if exists, name of the lens.
    Third  value in list that this function returns is a country where picture was taken.

    """
    chat_id = message.chat.id
    answer = []
    exif = exifread.process_file(image, details=False)
    if not len(exif.keys()):
        log.info('This picture doesn\'t contain EXIF.')
        return False

    # Convert EXIF data about location to decimal degrees
    exif_converter_result = get_coordinates_from_exif(exif, chat_id)
    # If tuple - there are coordinates, else - message to user
    if isinstance(exif_converter_result, tuple):
        coordinates = exif_converter_result
        answer.append(coordinates)
        lang = 'ru' if get_user_lang(chat_id) == 'ru-RU' else 'en'
        get_address_result = get_address(*coordinates, lang)
        try:
            address, country = get_address_result
        except TypeError:
            address, country = '', None
    else:
        # Add user message that photo doesn't have info about location or it can't be read
        address, country = '', None
        user_msg = exif_converter_result
        answer.append(user_msg)

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
    if country:
        save_user_query_info(camera_info, message, country)
    else:
        save_user_query_info(camera_info, message)

    others_with_this_cam = get_number_users_with_same_feature(camera, 'camera_name', chat_id)
    others_with_this_lens = get_number_users_with_same_feature(lens, 'lens_name', chat_id) if lens else None
    others_from_this_country = (get_number_users_with_same_feature(country[0], 'country_en', chat_id)
                                if country else None)

    info_about_shot = ''
    for tag, item in zip(lang_msgs[get_user_lang(chat_id)]['camera_info'], [date_time_str, camera, lens, address]):
        if item:
            info_about_shot += '*{}*: {}\n'.format(tag, item)

    info_about_shot += others_with_this_cam if others_with_this_cam else ''
    info_about_shot += '\n' + others_with_this_lens if others_with_this_lens else ''
    info_about_shot += '\n' + others_from_this_country if others_from_this_country else ''
    answer.append(info_about_shot)

    return [answer, camera_info, country]


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    chat_id = message.chat.id
    current_user_lang = get_user_lang(chat_id)
    bot.reply_to(message, lang_msgs[current_user_lang]['photo_prcs'])
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
    read_exif_result = read_exif(user_file, message)

    # Send to user message that there is no EXIF data in his picture
    if not read_exif_result:
        bot.reply_to(message, lang_msgs[current_user_lang]['no_exif'])
        return

    answer, cam_info, country = read_exif_result

    # Send location and info about shot back to user

    if isinstance(answer[0], tuple):
        lat, lon = answer[0]
        bot.send_location(chat_id, lat, lon, live_period=None)
        bot.reply_to(message, text=answer[1], parse_mode='Markdown')
        log_msg = ('Sent location and EXIF data back to Name: {} Last name: {} Nickname: '
                   '{} ID: {}'.format(message.from_user.first_name,
                                      message.from_user.last_name,
                                      message.from_user.username,
                                      message.from_user.id))

        log.info(log_msg)
        return

    # Sent to user only info about camera because there is no gps coordinates in his photo
    # user_msg consists of message that there is no info about location and messages with photo details
    user_msg = '{}\n{}'.format(answer[0], answer[1])

    bot.reply_to(message, user_msg, parse_mode='Markdown')
    log_msg = ('Sent only EXIF data back to Name: {} Last name: {} Nickname: '
               '{} ID: {}'.format(message.from_user.first_name,
                                  message.from_user.last_name,
                                  message.from_user.username,
                                  message.from_user.id))
    log.info(log_msg)


# I think you can safely cache several hundred or thousand of user-lang pairs without consuming to much memory,
# but for development purpose I will set it to some minimum to be sure that calling to DB works properly
if load_last_user_languages(10):
    log.info('Users languages were cached.')
else:
    log.warning('Couldn\'t cache users\' languages.')


def start_bot():
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

