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
from geopy.geocoders import Nominatim

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


def load_last_user_languages(max_users):
    """
    Function that caching user-lang pairs of last active users from database to pc memory
    :param max_users: number of entries to be cached
    :return: True if it complete work without errors, False otherwise
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
    row = cursor.execute(query)
    if row:
        last_active_users_tuple_of_tuples = cursor.fetchall()
        # Make list out of tuple of tuples that is returned by MySQL
        last_active_users = [chat_id[0] for chat_id in last_active_users_tuple_of_tuples]
    else:
        log.warning('There are no last active users')
        return False

    log.debug('Downloading languages for last active users from DB...')
    query = "SELECT chat_id, lang FROM user_lang_table WHERE chat_id in {};".format(tuple(last_active_users))
    row = None
    row = cursor.execute(query)
    if row:
        languages_of_users = cursor.fetchall()
        log.debug('Uploading users\' languages into memory...')
        for line in languages_of_users:
            log.debug('chat_id: {}, language: {}'.format(line[0], line[1]))
            user_lang[line[0]] = line[1]
        log.debug('Done')
        return True
    else:
        log.warning('There are now entries about user languages in database.')
        return False


def set_user_language(chat_id, lang):
    log.debug('Updating info about user {} language in memory & database...'.format(chat_id))
    query = 'UPDATE user_lang_table SET lang="{}" WHERE chat_id={}'.format(lang, chat_id)
    cursor.execute(query)
    db.commit()
    user_lang[chat_id] = lang
    log.info('User {} language was switched to {}'.format(chat_id, lang))


def get_user_lang(chat_id):
    """
    Function to look up user language in dictionary (which is like cache), than in database (if it is not in dict),
    then set language according to language code from telegram message object
    :param chat_id: telegram message object
    :return: language tag like ru-RU, en-US
    """
    log.info('Defining user {} language...'.format(chat_id))
    lang = user_lang.get(chat_id, None)
    if not lang:
        query = 'SELECT lang FROM user_lang_table WHERE chat_id={}'.format(chat_id)
        try:
            row = cursor.execute(query)
        except (MySQLdb.Error, MySQLdb.Warning) as e:
            lang = 'en-US'
            user_lang[chat_id] = lang
            return lang

        if row:
            lang = cursor.fetchone()[0]
            user_lang[chat_id] = lang
        else:
            lang = 'en-US'
            log.info('User {} default language for bot is set to be en-US.'.format(chat_id))
            query = 'INSERT INTO user_lang_table (chat_id, lang) VALUES ({}, "{}")'.format(chat_id, lang)
            cursor.execute(query)
            db.commit()
            user_lang[chat_id] = lang

    return lang


def change_user_language(chat_id):
    curr_lang = get_user_lang(chat_id)
    new_lang = 'ru-RU' if curr_lang == 'en-US' else 'en-US'
    log.info('Changing user {} language from {} to {}...'.format(chat_id, curr_lang, new_lang))
    try:
        set_user_language(chat_id, new_lang)
        return True
    except:
        log.error(traceback.format_exc())
        return False


def turn_bot_off():
    db_connector.disconnect()
    log.info('Please wait for a sec, bot is turning off...')
    bot.stop_polling()
    log.info('Auf Wiedersehen! Bot is turned off.')
    exit()


@bot.message_handler(commands=['start'])
def create_main_keyboard(arg):
    # arg can be integer that represent chat.id or message object from Telegram
    chat_id = arg if isinstance(arg, int) else arg.chat.id
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.row('Русский/English')
    markup.row(lang_msgs[get_user_lang(chat_id)]['top_cams'])
    markup.row(lang_msgs[get_user_lang(chat_id)]['top_lens'])
    markup.row(lang_msgs[get_user_lang(chat_id)]['top_countries'])
    bot.send_message(chat_id, lang_msgs[get_user_lang(chat_id)]['menu_header'], reply_markup=markup)


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def handle_menu_response(message):
    # keyboard_hider = telebot.types.ReplyKeyboardRemove()
    chat_id = message.chat.id
    if message.text == 'Русский/English':

        if change_user_language(chat_id):
            bot.send_message(chat_id, lang_msgs[get_user_lang(chat_id)]['switch_lang_success'])
            create_main_keyboard(chat_id)
        else:
            bot.send_message(chat_id, lang_msgs[get_user_lang(chat_id)]['switch_lang_failure'])
            create_main_keyboard(chat_id)

    elif message.text == lang_msgs[get_user_lang(chat_id)]['top_cams']:
        log.info('User {} asked for top cams'.format(chat_id))
        bot.send_message(chat_id, text=get_most_popular_cams_cached('camera_name', chat_id))
        log.info('List of most popular cameras has been returned to {} '.format(chat_id))

    elif message.text == lang_msgs[get_user_lang(chat_id)]['top_lens']:
        log.info('User {} asked for top lens'.format(chat_id))
        bot.send_message(chat_id, text=get_most_popular_lens_cached('lens_name', chat_id))
        log.info('List of most popular lens has been returned to {} '.format(chat_id))

    elif message.text == lang_msgs[get_user_lang(chat_id)]['top_countries']:
        log.info('User {} asked for top countries'.format(chat_id))
        table_name = 'country_ru' if get_user_lang(chat_id) == 'ru-RU' else 'country_en'
        bot.send_message(chat_id, text=get_most_popular_countries_cached(table_name, chat_id))
        log.info('List of most popular countries has been returned to {} '.format(chat_id))

    elif message.text == config.abort:
        bot.send_message(chat_id, lang_msgs[get_user_lang(chat_id)]['bye'])
        turn_bot_off()
    else:
        log.info('Name: {} Last name: {} Nickname: {} ID: {} sent text message.'.format(message.from_user.first_name,
                                                                                        message.from_user.last_name,
                                                                                        message.from_user.username,
                                                                                        message.from_user.id))

        # Answer to user that bot can't make a conversation with him
        bot.send_message(chat_id, lang_msgs[get_user_lang(chat_id)]['dont_speak'])


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


def cache_number_device_owners(func, cache_time):
    when_was_called = None
    result = {}

    def func_launcher(gadget_name, device_type, chat_id):
        nonlocal func
        nonlocal result
        nonlocal when_was_called

        # It's high time to call the function instead of cache
        # if countdown went off or if function has not been called yet.
        high_time = when_was_called + timedelta(minutes=cache_time) < datetime.now() if when_was_called else True
        if not when_was_called or high_time or gadget_name not in result:
            when_was_called = datetime.now()
            result[gadget_name] = func(gadget_name, device_type, chat_id)
            return result[gadget_name]
        else:
            log.info('Returning cached result of ' + func.__name__)
            time_left = when_was_called + timedelta(minutes=cache_time) - datetime.now()
            log.debug('Time to reevaluate result of {} is {}'.format( func.__name__, time_left))
            return result[gadget_name]

    return func_launcher


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
            log.debug('Time to reevaluate result of {} is {}'.format(func.__name__, time_left))
            return result

    return function_launcher


def get_address(latitude, longitude, lang):
    start_time = datetime.now()
    # Get address as a string by coordinats from photo that user sent to bot

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
        log.debug("It took {} seconds for get_address function to do the job".format((datetime.now() -
                                                                                      start_time).seconds))
        return location.address, (country_en, country_ru)
    except:
        log.error('Getting address failed!')
        log.error(traceback.format_exc())
        return False


def exif_to_dd(data, chat_id):
    # Convert exif gps to format that accepts Telegram (and Google Maps for example)

    try:
        # lat, lon = exif_to_dd(raw_coordinates)
        lat_ref = str(data['GPS GPSLatitudeRef'])
        lat = data['GPS GPSLatitude']
        lon_ref = str(data['GPS GPSLongitudeRef'])
        lon = data['GPS GPSLongitude']
    except KeyError:
        log.info('This picture doesn\'t contain coordinates.')
        return lang_msgs[get_user_lang(chat_id)]['no_gps']
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
        return [lang_msgs[get_user_lang(chat_id)]['bad_gps']]
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
                row = cursor.execute(query)
                if row:
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
        rows = cursor.execute(query)
        if not rows:
            log.info('Can\'t evaluate a list of the most popular items')
            return lang_msgs[get_user_lang(chat_id)]['no_top']

        popular_items = cursor.fetchall()
        if len(popular_items) > 30:
            log.info('Finish evalating the most popular items')
            return list_to_ordered_str_list(popular_items[:30])
        else:
            log.info('Finish evaluating the most popular items')
            return list_to_ordered_str_list(popular_items)
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        log.error(e)


# Make closures
get_most_popular_cams_cached = cache_func(get_most_popular_items, 5)
get_most_popular_lens_cached = cache_func(get_most_popular_items, 5)
get_most_popular_countries_cached = cache_func(get_most_popular_items, 5)


def get_number_users_by_gadget_name(gadget_name, device_type, chat_id):
    log.debug('Check how many users also have {}...'.format(gadget_name))
    answer = ''

    query = 'SELECT DISTINCT chat_id FROM photo_queries_table WHERE {}="{}"'.format(device_type, gadget_name)
    row = cursor.execute(query)
    if not row or row < 2:
        return None
    if device_type == 'camera_name':
        answer += lang_msgs[get_user_lang(chat_id)]['camera_users'] + str(row-1) + '.\n'
    elif device_type == 'lens_name':
        answer += lang_msgs[get_user_lang(chat_id)]['lens_users'] + str(row-1) + '.'

    return answer


# Make closure which preservers result of the function in order not to call database too often
get_number_all_owners_of_device = cache_number_device_owners(get_number_users_by_gadget_name, 30)


# Save camera info to database to collect statistics
def save_user_query_info(data, message, country=None):
    global db
    camera_name, lens_name = data
    camera_name = 'NULL' if not camera_name else '{0}{1}{0}'.format('"', camera_name)
    lens_name = 'NULL' if not lens_name else '{0}{1}{0}'.format('"', lens_name)
    chat_id = message.chat.id
    first_name = 'NULL' if not message.from_user.first_name else '{0}{1}{0}'.format('"', message.from_user.first_name)
    last_name = 'NULL' if not message.from_user.first_name else '{0}{1}{0}'.format('"', message.from_user.last_name)
    username = 'NULL' if not message.from_user.first_name else '{0}{1}{0}'.format('"', message.from_user.username)

    if not camera_name:
        log.warning('Something went wrong. There should be camera name to store it in database but there isn\'t')
        return

    try:
        log.info('Adding new entry to photo_queries_table...')
        if not country:
            country = ["NULL", "NULL"]
        query = ('INSERT INTO photo_queries_table (chat_id, camera_name, lens_name, first_name, last_name,'
                 ' username, country_en, country_ru) VALUES ({}, {}, {}, {}, {}, {}, '
                 '"{}", "{}")'.format(chat_id, camera_name, lens_name, first_name, last_name, username,
                                      country[0], country[1]))

        cursor.execute(query)
        db.commit()
    except (MySQLdb.Error, MySQLdb.Warning) as e:
        log.error(e)
        return


def read_exif(image, chat_id):
    """
    # Get various info about photo that user sent: time when picture was taken, location as longitude and latitude,
    # post address, type of camera/smartphone and lens, how many people have the same camera/lens.

    :param image: actual photo that user sent to bot
    :param chat_id: user id who ent photo and who bot should answer to
    :return: list with three values. First value called answer is also list that contains different information
    about picture. First value of answer is either tuple with coordinates from photo or string message
    that photo doesn't contain coordinates. Second value of answer is string with photo details: time, camera, lens
    from exif and, if any, messages how many other bot users have the same camera/lens.
    Second value in list that this function returns is camera info, which is list with one or two items: first is
    name of the samera/smartphone, second, if exists, name of the lens.
    Third  value in list that this function returns is a country where picture was taken.

    """
    answer = []
    exif = exifread.process_file(image, details=False)
    if not len(exif.keys()):
        log.info('This picture doesn\'t contain EXIF.')
        return False

    # Convert EXIF data about location to decimal degrees
    exif_converter_result = exif_to_dd(exif, chat_id)
    if isinstance(exif_converter_result, tuple):
        coordinates = exif_converter_result
        answer.append(coordinates)
        lang = 'ru' if get_user_lang(chat_id) == 'ru-RU' else 'en'
        get_address_result = get_address(*coordinates, lang)
        try:
            address, country = get_address_result
        except TypeError:
            address, country = '', False
    else:
        # Add user message that photo doesn't have info about location
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
    others_with_this_cam = get_number_all_owners_of_device(camera, 'camera_name', chat_id)
    others_with_this_lens = get_number_all_owners_of_device(lens, 'lens_name', chat_id) if lens else None
    camera_info = camera, lens

    info_about_shot = ''
    for tag, item in zip(lang_msgs[get_user_lang(chat_id)]['camera_info'], [date_time_str, camera, lens, address]):
        if item:
            info_about_shot += '*{}*: {}\n'.format(tag, item)

    info_about_shot += others_with_this_cam if others_with_this_cam else ''
    info_about_shot += others_with_this_lens if others_with_this_lens else ''
    answer.append(info_about_shot)

    return [answer, camera_info, country]


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    chat_id = message.chat.id
    bot.reply_to(message, lang_msgs[get_user_lang(chat_id)]['photo_prcs'])
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
    read_exif_result = read_exif(user_file, chat_id)

    # Send to user message that there is no EXIF data in his picture
    if not read_exif_result:
        bot.reply_to(message, lang_msgs[get_user_lang(chat_id)]['no_exif'])
        return

    answer, cam_info, country = read_exif_result
    # Send location and info about shot back to user
    # if len(answer[0]) == 2:
    #     log.debug(answer[0])

    if isinstance(answer[0], tuple):
        lat, lon = answer[0]
        # log.debug(lat)
        # log.debud(lon)
        bot.send_location(chat_id, lat, lon, live_period=None)
        bot.reply_to(message, text=answer[1], parse_mode='Markdown')
        log_msg = ('Sent location and EXIF data back to Name: {} Last name: {} Nickname: '
                   '{} ID: {}'.format(message.from_user.first_name,
                                      message.from_user.last_name,
                                      message.from_user.username,
                                      message.from_user.id))

        log.info(log_msg)
        save_user_query_info(cam_info, message, country)
        return

    # Sent to user only info about shot because there is no gps coordinates in his shot
    # user_msg consists of message that there is no info about location and messages with photo details
    user_msg = '{}\n{}'.format(answer[0], answer[1])

    bot.reply_to(message, user_msg, parse_mode='Markdown')
    log_msg = ('Sent only EXIF data back to Name: {} Last name: {} Nickname: '
               '{} ID: {}'.format(message.from_user.first_name,
                                  message.from_user.last_name,
                                  message.from_user.username,
                                  message.from_user.id))
    log.info(log_msg)
    save_user_query_info(cam_info, message)


# I think you can safely cache several hundred or thousand of user-lang pairs without consuming to much memory,
# but for development purpose I will set it to some minimum to be sure that calling to DB works properly
if load_last_user_languages(5):
    log.info('Users languages were cached.')
else:
    log.warning('Couldn\'t cache users\' languages.')


bot.polling(none_stop=True, timeout=90)  # Keep bot receiving messages
# # If bot crashes, try to restart and send me a message
# def telegram_polling(state):
#     try:
#         bot.polling(none_stop=True, timeout=90)  # Keep bot receiving messages
#         if state == 'recovering':
#             bot.send_message(config.me, text='Bot has restarted after critical error.')
#     except:
#         # db_connector.disconnect()
#         # log.warning('Bot crashed with:\n' + traceback.format_exc())
#         bot.stop_polling()
#         for i in range(30, 0, -1):
#             print(str(i) + ' seconds to restart...')
#             time.sleep(1)
#         telegram_polling('recovering')

#
# if __name__ == '__main__':
#     telegram_polling('OK')
