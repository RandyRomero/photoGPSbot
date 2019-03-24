"""
Small bot for Telegram that receives your photo and returns you map where
it was taken.
Written by Aleksandr Mikheev.
https://github.com/RandyRomero/photogpsbot

This specific module contains methods to respond user messages, to make
interactive menus, to handle user language, to process user images
"""

# todo check what is wrong with geopy on
#  last versions (some deprecation warning)

# todo rewrite the processing of images
# todo update docstrings and comments

import os
from io import BytesIO
import traceback
from datetime import datetime, timedelta

from telebot import types
import exifread
import requests
from geopy.geocoders import Nominatim

from photogpsbot import bot, log, log_files, db, users, messages
import config


def get_admin_stat(command):
    # Function that returns statistics to admin by command
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

        query = ('SELECT chat_id '
                 'FROM photo_queries_table2 '
                 'GROUP BY chat_id '
                 'ORDER BY MAX(time) '
                 'DESC LIMIT 100')

        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        chat_ids = cursor.fetchall()
        bot_users = ''
        i = 1
        for chat_id in chat_ids:
            user = users.find_one(chat_id=chat_id[0])
            if not user:
                continue
            bot_users += f'{i}. {user}\n'
            i += 1
        answer = ('Up to 100 last active users by the time when they sent '
                  'picture last time:\n')
        answer += bot_users
        log.info('Done.')
        return answer

    elif command == 'total number photos sent':
        log.info('Evaluating total number of photo queries in database...')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table2')
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += '{} times users sent photos.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table2 '
                 'WHERE chat_id !={}'.format(config.MY_TELEGRAM))
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'photos today':
        # Show how many photos have been sent since 00:00:00 of today
        log.info('Evaluating number of photos which were sent today.')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table2 '
                 'WHERE time > "{}"'.format(today))
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += f'{cursor.fetchone()[0]} times users sent photos today.'
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table2 '
                 'WHERE time > "{}" '
                 'AND chat_id !={}'.format(today, config.MY_TELEGRAM))
        cursor = db.execute_query(query)
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
                 'FROM photo_queries_table2')
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += 'There are totally {} users.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(DISTINCT chat_id) '
                 'FROM photo_queries_table2 '
                 'WHERE time > "{}"'.format(today))
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += f'\n{cursor.fetchone()[0]} users have sent photos today.'
        log.info('Done.')
        return answer

    elif command == 'number of gadgets':
        # To show you number smartphones + cameras in database
        log.info('Evaluating number of cameras and smartphones in database...')
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table2')
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += (f'There are totally {cursor.fetchone()[0]} '
                   f'cameras/smartphones.')
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table2 '
                 'WHERE time > "{}"'.format(today))
        cursor = db.execute_query(query)
        if not cursor:
            return error_answer
        answer += (f'\n{cursor.fetchone()[0]} cameras/smartphones '
                   'were used today.')
        log.info('Done.')
        return answer

    elif command == 'uptime':
        fmt = 'Uptime: {} days, {} hours, {} minutes and {} seconds.'
        td = datetime.now() - bot.start_time
        # datetime.timedelta.seconds returns you total number of seconds
        # since given time, so you need to perform
        # a little bit of math to make whole hours, minutes and seconds from it
        # And there isn't any normal way to do it in Python unfortunately
        uptime = fmt.format(td.days, td.seconds // 3600, td.seconds % 3600 //
                            60, td.seconds % 60)
        log.info(uptime)
        return uptime


@bot.message_handler(commands=['start'])
def create_main_keyboard(message):
    user = users.find_one(message)
    current_user_lang = user.language
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True,
                                       resize_keyboard=True)
    markup.row('Русский/English')
    markup.row(messages[current_user_lang]['top_cams'])
    markup.row(messages[current_user_lang]['top_lens'])
    markup.row(messages[current_user_lang]['top_countries'])
    bot.send_message(user.chat_id, messages[current_user_lang]['menu_header'],
                     reply_markup=markup)


# Decorator to handle text messages
@bot.message_handler(content_types=['text'])
def handle_menu_response(message):
    # keyboard_hider = telebot.types.ReplyKeyboardRemove()
    current_user_lang = users.find_one(message).language
    user = users.find_one(message)

    if message.text == 'Русский/English':

        new_lang = users.find_one(message).switch_language()
        if current_user_lang != new_lang:
            bot.send_message(user.chat_id, messages[new_lang]
                             ['switch_lang_success'])
            create_main_keyboard(message)
        else:
            bot.send_message(user.chat_id, messages[new_lang]
                             ['switch_lang_failure'])
            create_main_keyboard(message)

    elif message.text == messages[current_user_lang]['top_cams']:
        log.info('User %s asked for top cams', user)
        bot.send_message(user.chat_id,
                         text=get_most_popular_items('camera_name', message))
        log.info('List of most popular cameras '
                 'has been returned to %s', user)

    elif message.text == messages[current_user_lang]['top_lens']:
        log.info('User %s asked for top lens', user)
        bot.send_message(user.chat_id,
                         text=get_most_popular_items('lens_name',
                                                     message))
        log.info('List of most popular lens has been returned to %s', user)

    elif message.text == messages[current_user_lang]['top_countries']:
        log.info('User %s asked for top countries', user)
        lang_table_name = ('country_ru'
                           if current_user_lang == 'ru-RU'
                           else 'country_en')
        bot.send_message(user.chat_id,
                         text=get_most_popular_items(lang_table_name, message))
        log.info('List of most popular countries has '
                 'been returned to %s', user)

    elif (message.text.lower() == 'admin' and
          user.chat_id == int(config.MY_TELEGRAM)):
        # Creates inline keyboard with options for admin Function that handle
        # user interaction with the keyboard called admin_menu

        keyboard = types.InlineKeyboardMarkup()  # Make keyboard object
        button = types.InlineKeyboardButton  # just an alias to save space

        keyboard.add(button(text='Turn bot off', callback_data='off'))
        keyboard.add(button(text='Last active users',
                            callback_data='last active'))
        keyboard.add(button(text='Total number of photos were sent',
                            callback_data='total number photos sent'))
        keyboard.add(button(text='Number of photos today',
                            callback_data='photos today'))
        keyboard.add(button(text='Number of users',
                            callback_data='number of users'))
        keyboard.add(button(text='Number of gadgets',
                            callback_data='number of gadgets'))
        keyboard.add(button(text='Uptime', callback_data='uptime'))
        bot.send_message(config.MY_TELEGRAM,
                         'Admin commands', reply_markup=keyboard)

    else:
        log.info('%s sent text message.', user)

        # Answer to user that bot can't make a conversation with him
        bot.send_message(user.chat_id,
                         messages[current_user_lang]['dont_speak'])


@bot.callback_query_handler(func=lambda call: True)
def admin_menu(call):  # Respond commands from admin menu
    # Remove progress bar from pressed button
    bot.answer_callback_query(callback_query_id=call.id, show_alert=False)

    if call.data == 'off':
        if db.disconnect():
            bot.turn_off()
        else:
            log.error('Cannot stop bot.')
            bot.send_message(chat_id=config.MY_TELEGRAM,
                              text='Cannot stop bot.')
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
    user = users.find_one(message)
    bot.send_message(user.chat_id, messages[user.language]['as_file'])
    log.info('%s sent photo as a photo.', user)


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

    def func_launcher(feature_name, device_type, message):
        nonlocal func
        nonlocal result
        nonlocal when_was_called
        cache_time = 5

        # Make id in order to cache and return
        # result by feature_type and language of user
        result_id = '{}_{}'.format(feature_name,
                                   users.find_one(message).language)

        # It's high time to reevaluate result instead
        # of just looking up in cache if countdown went off, if
        # function has not been called yet, if result for
        # feature (like camera, lens or country) not in cache
        high_time = (when_was_called + timedelta(minutes=cache_time) <
                     datetime.now() if when_was_called else True)

        if not when_was_called or high_time or result_id not in result:
            when_was_called = datetime.now()
            result[result_id] = func(feature_name, device_type, message)
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

    def function_launcher(item_type, message):
        nonlocal func
        nonlocal result
        nonlocal when_was_called
        cache_time = 5

        # Only top countries can be returned in different languages.
        # For the other types of queries it doesn't mean a thing.
        if item_type == 'country_ru' or item_type == 'country_en':
            result_id = users.find_one(message).language + item_type
        else:
            result_id = item_type

        # evaluate boolean whether it is high time to call given function or
        # not
        high_time = (when_was_called + timedelta(minutes=cache_time) <
                     datetime.now() if when_was_called else True)

        if not result.get(result_id, None) or not when_was_called or high_time:
            when_was_called = datetime.now()
            result[result_id] = func(item_type, message)
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


def get_coordinates_from_exif(data, message):
    """
    # Convert GPS coordinates from format in which they are stored in
    EXIF of photo to format that accepts Telegram (and Google Maps for example)

    :param data: EXIF data extracted from photo
    :param message: telebot object with info about user and his message
    :return: either floats that represents longitude and latitude or
    string with error message dedicated to user
    """

    current_user_lang = users.find_one(message).language

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
            cursor = db.execute_query(query)
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
def get_most_popular_items(item_type, message):
    """
    Get most common cameras/lenses/countries from database and
    make list of them
    :param item_type: string with column name to choose between cameras,
    lenses and countries
    :param message: telebot object with info about user and his message
    :return: string which is either list of most common
    cameras/lenses/countries or message which states that list is
    empty
    """

    user = users.find_one(message)

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
    query = ('SELECT {0} FROM photo_queries_table2 '
             'GROUP BY {0} '
             'ORDER BY count({0}) '
             'DESC'.format(item_type))
    cursor = db.execute_query(query)
    if not cursor:
        log.error("Can't evaluate a list of the most popular items")
        return messages[user.language]['doesnt work']
    if not cursor.rowcount:
        log.warning('There is nothing in the main database table')
        bot.send_message(chat_id=config.MY_TELEGRAM,
                         text='There is nothing in the main database table')
        return messages[user.language]['no_top']

    popular_items = cursor.fetchall()
    if len(popular_items) > 30:
        log.info('Finish evaluating the most popular items')
        return list_to_ordered_str_list(popular_items[:30])
    else:
        log.info('Finish evaluating the most popular items')
        return list_to_ordered_str_list(popular_items)


@cache_number_users_with_same_feature
def get_number_users_by_feature(feature_name, feature_type, message):
    """
    Get number of users that have same smartphone, camera, lens or that
    have been to the same country
    :param feature_name: string which is name of a particular feature e.g.
    camera name or country name
    :param feature_type: string which is name of the column in database
    :param message: telebot object with info about message and its sender
    :return: string which is message to user
    """
    log.debug('Check how many users also have feature: %s...', feature_name)

    user = users.find_one(message)
    current_user_lang = user.language
    answer = ''
    query = ('SELECT DISTINCT chat_id '
             'FROM photo_queries_table2 '
             'WHERE {}="{}"'.format(feature_type, feature_name))
    cursor = db.execute_query(query)
    if not cursor or not cursor.rowcount:
        return None
    row = cursor.rowcount

    if feature_type == 'camera_name':
        # asterisks for markdown - to make font bold
        answer += '*{}*{}.'.format(messages[current_user_lang]
                                   ['camera_users'], str(row-1))
    elif feature_type == 'lens_name':
        answer += '*{}*{}.'.format(messages[current_user_lang]
                                   ['lens_users'], str(row - 1))
    elif feature_type == 'country_en':
        answer += '*{}*{}.'.format(messages[current_user_lang]
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
    user = users.find_one(message)

    if not country:
        country_en = country_ru = 'NULL'
    else:
        country_en = '"{}"'.format(country[0])
        country_ru = '"{}"'.format(country[1])

    log.info("Adding user's query to photo_queries_table2...")

    query = ('INSERT INTO photo_queries_table2 (chat_id, camera_name, '
             f'lens_name, country_en, country_ru) VALUES ({user.chat_id}, '
             f'{camera_name}, {lens_name}, {country_en}, {country_ru})')

    if not db.add(query):
        log.warning("Cannot add user's query into database")
        return

    log.info("User's query was successfully added to the database.")
    return


def read_exif(image, message):
    """
    Get various info about photo that user sent: time when picture was taken,
    location as longitude and latitude, post address, type of
    camera/smartphone and lens, how many people have
    the same camera/lens.

    :param image: actual photo that user sent to bot
    :param message: telebot object with info about user and his message
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
    user = users.find_one(message)
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

    exif_converter_result = get_coordinates_from_exif(exif, message)
    # If tuple - there are coordinates, else - message to user t
    # hat there are no coordinates
    if isinstance(exif_converter_result, tuple):
        coordinates = exif_converter_result
        answer.append(coordinates)
        lang = 'ru' if user.language == 'ru-RU' else 'en'
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
                                                       'camera_name', message)

    others_with_this_lens = (
        get_number_users_by_feature(lens, 'lens_name', message)
        if lens else None)

    others_from_this_country = (
        get_number_users_by_feature(country[0], 'country_en', message)
        if country else None)

    # Make user message about camera from exif
    info_about_shot = ''
    for tag, item in zip(messages[user.language]['camera_info'],
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
    user = users.find_one(message)
    bot.reply_to(message, messages[user.language]['photo_prcs'])
    log.info('%s sent photo as a file.', user)

    file_id = bot.get_file(message.document.file_id)
    # Get temporary link to a photo that user has sent to bot
    file_path = file_id.file_path
    # Download photo that got telegram bot from user
    # todo fix this (we don't use prod anymore)
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
        log.info('The photo does not contain EXIF')
        bot.reply_to(message, messages[user.language]['no_exif'])
        return

    answer, cam_info, country = read_exif_result

    # Send location and info about shot back to user
    if isinstance(answer[0], tuple):
        lat, lon = answer[0]
        bot.send_location(user.chat_id, lat, lon, live_period=None)
        bot.reply_to(message, text=answer[1], parse_mode='Markdown')

        log.info('Sent location and EXIF data back to %s', user)
        return

    # Sent to user only info about camera because there is no gps
    # coordinates in his photo
    user_msg = '{}\n{}'.format(answer[0], answer[1])
    bot.reply_to(message, user_msg, parse_mode='Markdown')
    log.info('Sent only EXIF data back to %s ', user)


def main():
    log_files.clean_log_folder(1)
    users.cache(100)
    db.connect()
    bot.start_bot()


if __name__ == '__main__':
    main()
