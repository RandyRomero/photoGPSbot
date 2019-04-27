"""
Small bot for Telegram that receives your photo and returns you a map with
location where the photo was taken.
Written by Aleksandr Mikheev.
https://github.com/RandyRomero/photogpsbot

This specific module contains methods to respond user messages, to make
interactive menus, to handle user language, to process user images
"""

# todo check what is wrong with geopy on
#  last versions (some deprecation warning)

# todo update docstrings and comments
# todo rewrite admin stat as a class
from io import BytesIO
from datetime import datetime, timedelta

# telebot goes as pyTelegramBotAPI in requirements
from telebot import types
import requests

from photogpsbot import bot, log, log_files, db, User, users, messages, machine
from photogpsbot.process_image import ImageHandler, ImageData
from photogpsbot.db_connector import DatabaseConnectionError
import config

from typing import List, Tuple, Callable
from telebot.types import Message, CallbackQuery

CACHE_TIME = config.CACHE_TIME


class PhotoMessage:
    """
    Class that handles user message with a photo. It opens it, gets info from
    it (via another class), saves info about the photo to the database, finds
    out how many other users have the same camera, lens or took a photo from
    the same country. Finally, prepares prepares an answer with this info to
    be send back to user.
    """
    def __init__(self, message, user):
        """
        init variables
        :param message: Message object from Telebot
        :param user: User object that represents one particular user
        """
        self.message = message
        self.user = user
        self.image_handler = ImageHandler

    @staticmethod
    def open_photo(message):
        """
        Method that gets from Telegram link to the file, downloads it, opens
        it like file-like object that will be proceed later by this bot
        :param message: Message object from Telebot that represents a
        Telegram message
        :return: file-like object of a photo that user sent
        """

        # Get temporary link to a photo that user sends to the bot
        file_path = bot.get_file(message.document.file_id).file_path

        # Download photo that got the bot from a user
        link = ("https://api.telegram.org/file/"
                f"bot{config.TELEGRAM_TOKEN}/{file_path}")

        if machine == 'prod':
            r = requests.get(link)
        else:
            # use proxy if the bot is running not on production server
            proxies = {'https': config.PROXY_CONFIG}
            r = requests.get(link, proxies=proxies)

        # Get and return file-like object of user's photo
        return BytesIO(r.content)

    def get_info(self):
        """
        Opens file that user sent as a file-like object, get necessary info
        from it and return this info

        :return: instance of ImageData - my dataclass for storing info about
        an image like user, date, camera name etc
        """
        user_photo = self.open_photo(self.message)
        image = self.image_handler(self.user, user_photo)
        return image.get_image_info()

    def save_info_to_db(self, image_data):
        """
           When user sends photo as a file to get information, bot also stores
           information about this query to the database to keep statistics that
           can be shown to a user in different ways. It stores time of query,
           Telegram id of a user, his camera and lens which were used for
           taking photo, his first and last name, nickname and country where
           the photo was taken. The bot does not save photos or their
           coordinates.

           :image_data: an instance of ImageData dataclass with info about
           the image
           :return: None
           """
        camera_name, lens_name = image_data.camera, image_data.lens
        camera_name = f'"{camera_name}"' if camera_name else None
        lens_name = f'"{lens_name}"' if lens_name else None

        if not image_data.country:
            country_en = country_ru = None
        else:
            country_en = f'"{image_data.country["en-US"]}"'
            country_ru = f'"{image_data.country["ru-RU"]}"'

        log.info('Adding user query to photo_queries_table...')

        query = ('INSERT INTO photo_queries_table '
                 '(chat_id, camera_name, lens_name, country_en, country_ru) '
                 'VALUES (%s, %s, %s, %s, %s)')

        parameters = (self.user.chat_id, camera_name, lens_name, country_en,
                      country_ru)

        db.execute_query(query, parameters)
        db.conn.commit()
        log.info('User query was successfully added to the database.')

    @staticmethod
    def find_num_users_with_same_feature(image_data: ImageData) -> List[int]:
        """
        Finds how many users have the same camera, or lens, or took a photo
        from the same country
        :param image_data: object with info about a photo that some user
        sent
        :return: list with integers where first integer is a number of people
        how have the same camera, second - numbers of users who have the same
        lens, the third - number of users who took a photo from the same
        country
        """
        same_feature = []

        feature_types = ('camera_name', 'lens_name', 'country_en')
        features = (image_data.camera, image_data.lens,
                    image_data.country['en-US'])

        for feature_name, feature in zip(feature_types, features):
            if not feature:
                same_feature.append(0)
                continue
            answer = get_number_users_by_feature(feature, feature_name)
            same_feature.append(answer)

        return same_feature

    def prepare_answer(self) -> Tuple[Tuple[float, float], str]:
        """
        Get info from a photo that user sent, save the data to the
        database, make an answer to be sent via Telegram

        :return: a tuple where the first value is a tuple that contains
        coordinates of a photo, the second is a string with message to user
        with info about his photo
        """

        # Get instance of the dataclass ImageData with info about the image
        image_data = self.get_info()
        # Save some general info about the user's query to the database
        self.save_info_to_db(image_data)

        answer = ''
        coordinates = image_data.latitude, image_data.longitude
        if not coordinates[0]:
            answer += messages[self.user.language]["no_gps"]

        answ_template = messages[self.user.language]["camera_info"]
        basic_data = (image_data.date_time, image_data.camera, image_data.lens,
                      image_data.address[self.user.language])

        # Concatenate templates in language that user prefer with information
        # from the photo, for example: f'{"Camera brand"}:{"Canon 60D"}'
        for arg in zip(answ_template, basic_data):
            if arg[1]:
                answer += f'*{arg[0]}*: {arg[1]}\n'

        lang = self.user.language
        lang_templates = messages[lang]["users with the same feature"].values()
        ppl_wth_same_featrs = self.find_num_users_with_same_feature(image_data)
        for template, feature in zip(lang_templates, ppl_wth_same_featrs):
            if feature:
                answer += f'{template} {feature}\n'

        return coordinates, answer


def get_admin_stat(command: str) -> str:
    """
    Function that returns statistics to admin by command
    :param command: string with a command what kind of statistics to prepare
    :return: a string with either answer with statistics or an error message
    """
    error_answer = "Can't execute your command. Check logs"
    answer = 'There is some statistics for you: \n'

    # Set to a beginning of the day
    today = (datetime
             .today()
             .replace(hour=0, minute=0, second=0, microsecond=0)
             .strftime('%Y-%m-%d %H:%M:%S'))

    # Last users with date of last time when they used bot
    if command == 'last active users':

        try:
            last_active_users = users.get_last_active_users(100)
        except DatabaseConnectionError:
            return error_answer

        bot_users = ''
        # Makes a human readable list of last active users
        for usr, index in zip(last_active_users,
                              range(len(last_active_users))):
            user = User(*usr)
            bot_users += f'{index + 1}. {user}\n'

        answer = ('Up to 100 last active users by the time when they sent '
                  'picture last time:\n')
        answer += bot_users
        log.info('Done.')
        return answer

    elif command == 'total number photos sent':
        log.info('Evaluating total number of photo queries in database...')
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table2')
        try:
            cursor = db.execute_query(query)
        except DatabaseConnectionError:
            return error_answer
        answer += '{} times users sent photos.'.format(cursor.fetchone()[0])
        query = ('SELECT COUNT(chat_id) '
                 'FROM photo_queries_table2 '
                 'WHERE chat_id !=%s')
        parameters = (config.MY_TELEGRAM,)
        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            answer += ("\nCannot calculate number of photos that were send "
                       "excluding your photos. Check logs")
            return answer

        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'photos today':
        # Show how many photos have been sent since 00:00:00 of today
        log.info('Evaluating number of photos which were sent today.')
        query = ("SELECT COUNT(chat_id) "
                 "FROM photo_queries_table2 "
                 "WHERE time > %s")

        parameters = (today,)

        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            return error_answer
        answer += f'{cursor.fetchone()[0]} times users sent photos today.'
        query = ("SELECT COUNT(chat_id) "
                 "FROM photo_queries_table2 "
                 "WHERE time > %s "
                 "AND chat_id !=%s")

        parameters = today, config.MY_TELEGRAM

        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            return error_answer

        answer += '\nExcept you: {} times.'.format(cursor.fetchone()[0])
        log.info('Done.')
        return answer

    elif command == 'number of users':
        # Show number of users who has used bot at leas"
        # once or more (first for the whole time, then today)
        log.info('Evaluating number of users that use bot '
                 'since the first day and today...')
        try:
            num_of_users = users.get_total_number()
        except DatabaseConnectionError:
            return error_answer

        answer += f'There are totally {num_of_users} users.'

        query = ("SELECT COUNT(DISTINCT chat_id) "
                 "FROM photo_queries_table2 "
                 "WHERE time > %s")

        parameters = (today,)
        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            answer += ("\nCannot calculate how many user have sent their "
                       "photos today")
            return answer

        answer += f'\n{cursor.fetchone()[0]} users have sent photos today.'
        log.info('Done.')
        return answer

    elif command == 'number of gadgets':
        # To show you number smartphones + cameras in database
        log.info('Evaluating number of cameras and smartphones in database...')
        query = ('SELECT COUNT(DISTINCT camera_name) '
                 'FROM photo_queries_table2')
        try:
            cursor = db.execute_query(query)
        except DatabaseConnectionError:
            return error_answer
        answer += (f'There are totally {cursor.fetchone()[0]} '
                   f'cameras/smartphones.')
        query = ("SELECT COUNT(DISTINCT camera_name) "
                 "FROM photo_queries_table2 "
                 "WHERE time > %s")
        parameters = (today,)
        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            answer += ("Cannot calculate the number of gadgets that have been "
                       "used today so far")
            return answer

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
def create_main_keyboard(message: Message) -> None:
    """
    Creates and renders a main keyboard
    :param message: message from a user
    :return: None
    """

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
def handle_menu_response(message: Message) -> None:
    """
    Function that handles user's respond to the main keyboard
    :param message: user's message
    :return: None
    """

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

        # in order not to check whether user has changed his nickname or
        # whatever every time his sends any request the bot will just check
        # it every time a user wants to get a statistic about the most
        # popular cameras
        users.compare_and_update(user, message)

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
def admin_menu(call: CallbackQuery) -> None:
    """
    Respond to commands from admin menu

    :param call: object that contains info about user's reaction to an
    interactive keyboard

    :return: None
    """

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
def answer_photo_message(message: Message) -> None:
    """
    Handles situations when user sends a photo as a photo not as a file,
    namely answers to him that he need to send his photo as a file

    :param message: Message objects from Telebot that contains all the data
    about user's message
    :return: none
    """
    user = users.find_one(message)
    bot.send_message(user.chat_id, messages[user.language]['as_file'])
    log.info('%s sent photo as a photo.', user)


def cache_number_users_with_same_feature(func: Callable) -> Callable:
    """
    This is a decorator to cache previous results of a given function so to
    not to call a database to much. It saves its result in a dictionary

    :param func: any function which result you want to cache in order no to
    call original function to often
    :return: closure with a given function that was decorated by func_launcher
    """

    when_was_called = None
    storage = {}

    def func_launcher(feature: str, feature_type: str) -> int:
        """
        Function that calls a given function if it is high time otherwise it
        returns previous result stored in a dictionary called 'storage'

        :param feature: string which is name of a particular feature e.g.
        camera name or country name
        :param feature_type: string which is name of the column in database
        :return: the result of a given function
        """
        nonlocal when_was_called

        # It's high time to reevaluate result instead of just looking up in
        # cache if countdown went off, if function has not been called yet, if
        # result for a feature (like camera, lens or country) not in cache
        high_time = (when_was_called + timedelta(minutes=CACHE_TIME) <
                     datetime.now() if when_was_called else True)

        if not when_was_called or high_time or feature not in storage:
            when_was_called = datetime.now()
            result = func(feature, feature_type)
            storage[feature] = result
            return result
        else:
            log.info('Returning cached result of %s',  func.__name__)
            time_left = (when_was_called + timedelta(minutes=CACHE_TIME) -
                         datetime.now())
            log.debug('Time to to reevaluate result of %s is %s',
                      func.__name__, str(time_left)[:-7])
            return storage[feature]

    return func_launcher


def cache_most_popular_items(func: Callable) -> Callable:
    """
    Function that prevent calling any given function more often than once in
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
        nonlocal when_was_called

        # Only top countries can be returned in different languages.
        # For the other types of queries it doesn't mean a thing.
        if item_type == 'country_ru' or item_type == 'country_en':
            result_id = users.find_one(message).language + item_type
        else:
            result_id = item_type

        # evaluate boolean whether it is high time to call given function or
        # not
        high_time = (when_was_called + timedelta(minutes=CACHE_TIME) <
                     datetime.now() if when_was_called else True)

        if not result.get(result_id, None) or not when_was_called or high_time:
            when_was_called = datetime.now()
            result[result_id] = func(item_type, message)
            return result[result_id]
        else:
            log.debug('Return cached result of %s...', func.__name__)
            time_left = (when_was_called + timedelta(minutes=CACHE_TIME) -
                         datetime.now())
            log.debug('Time to reevaluate result of %s is %s',
                      func.__name__, str(time_left)[:-7])
            return result[result_id]

    return function_launcher


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

    query = (f'SELECT {item_type} FROM photo_queries_table2 '
             f'GROUP BY {item_type} '
             f'ORDER BY count({item_type}) '
             'DESC')

    try:
        cursor = db.execute_query(query)
    except DatabaseConnectionError:
        log.error("Can't evaluate a list of the most popular items")
        return messages[user.language]['doesnt work']

    # Almost impossible case but still
    if not cursor.rowcount:
        log.warning('There is nothing in the main database table')
        bot.send_message(chat_id=config.MY_TELEGRAM,
                         text='There is nothing in the main database table')
        return messages[user.language]['no_top']

    popular_items = cursor.fetchall()
    log.info('Finish evaluating the most popular items')
    return list_to_ordered_str_list(popular_items[:30])


@cache_number_users_with_same_feature
def get_number_users_by_feature(feature: str, feature_type: str) -> int:
    """
    Get number of users that have same smartphone, camera, lens or that
    have been to the same country
    :param feature: string which is name of a particular feature e.g.
    camera name or country name
    :param feature_type: string which is name of the column in database
    :return: string which is message to user
    """
    log.debug('Check how many users also have this feature: %s...',
              feature)

    query = ("SELECT DISTINCT chat_id "
             "FROM photo_queries_table2 "
             "WHERE %s=%s")

    parameters = (feature_type, feature)

    try:
        cursor = db.execute_query(query, parameters)
    except DatabaseConnectionError:
        log.error("Cannot check how many users also have this feature: %s...",
                  feature)
        raise

    if not cursor.rowcount:
        log.debug('There were no users with %s...', feature)
        return 0

    log.debug('There is %d users with %s', cursor.rowcount, feature)
    return cursor.rowcount - 1


@bot.message_handler(content_types=['document'])  # receive file
def handle_message_with_image(message):

    user = users.find_one(message)
    # Sending a message to a user that his photo is being processed
    bot.reply_to(message, messages[user.language]['photo_prcs'])
    log.info('%s sent photo as a file.', user)

    photo_message = PhotoMessage(message, user)
    answer = photo_message.prepare_answer()

    # if longitude is in the answer
    if answer[0][0]:
        lon = answer[0][0]
        lat = answer[0][1]
        bot.send_location(user.chat_id, lon, lat, live_period=None)
        bot.reply_to(message, answer[1], parse_mode='Markdown')
    else:
        bot.reply_to(message, answer, parse_mode='Markdown')


def main():
    log_files.clean_log_folder(1)
    users.cache(100)
    db.connect()
    bot.start_bot()


if __name__ == '__main__':
    main()
