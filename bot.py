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
from datetime import datetime
import handle_logs
import language_pack
import db_connector

logFile, logConsole = handle_logs.set_loggers()  # set up logging via my module
bot = telebot.TeleBot(config.token)
lang = language_pack.language_ru


@bot.message_handler(commands=['language', 'start'])
def choose_language(message):
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    rus = types.KeyboardButton(text='Русский')
    en = types.KeyboardButton(text='English')
    keyboard.add(rus, en)
    bot.send_message(message.chat.id, text='Выбери язык / Choose language', reply_markup=keyboard)


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def answer_text_message(message):
    global lang
    keyboard_hider = telebot.types.ReplyKeyboardRemove()
    if message.text == 'Русский':
        lang = language_pack.language_ru
        bot.send_message(message.chat.id, text='Вы выбрали русский язык.', reply_markup=keyboard_hider)
    elif message.text == 'English':
        lang = language_pack.language_en
        bot.send_message(message.chat.id, text='You chose English.', reply_markup=keyboard_hider)

    else:
        # Function that echos all users messages
        bot.send_message(message.chat.id, lang['dont_speak'])
        log_msg = ('Name: {} Last name: {} Nickname: {} ID: {} sent text message.'.format(message.from_user.first_name,
                                                                                          message.from_user.last_name,
                                                                                          message.from_user.username,
                                                                                          message.from_user.id))
        logFile.info(log_msg)
        logConsole.info(log_msg)


@bot.message_handler(content_types=['photo'])
def answer_photo_message(message):
    bot.send_message(message.chat.id, lang['as_file'])
    log_message = ('Name: {} Last name: {} Nickname: {} ID: {} sent '
                   'photo as a photo.'.format(message.from_user.first_name,
                                              message.from_user.last_name,
                                              message.from_user.username,
                                              message.from_user.id))

    logFile.info(log_message)
    logConsole.info(log_message)


def exif_to_dd(data):
    # Convert exif gps to format that accepts Telegram (and Google Maps for example)

    try:
        # lat, lon = exif_to_dd(raw_coordinates)
        lat_ref = str(data['GPS GPSLatitudeRef'])
        lat = data['GPS GPSLatitude']
        lon_ref = str(data['GPS GPSLongitudeRef'])
        lon = data['GPS GPSLongitude']
    except KeyError:
        logFile.info('This picture doesn\'t contain coordinates.')
        logConsole.info('This picture doesn\'t contain coordinates.')

        return [lang['no_gps']]
        # TODO Save exif of photo if converter catch an error trying to convert gps data

    def idf_tag_to_coordinate(tag):
        try:
            # convert ifdtag from exifread module to decimal degree format of coordinate
            tag = str(tag).replace('[', '').replace(']', '').split(',')
            tag[2] = int(tag[2].split('/')[0]) / int(tag[2].split('/')[1])
            return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600
        except TypeError:
            # Save GPS data which led to error
            logFile.info('GPS-Converter has crushed. Saving gps data from the photo to logs...')
            logFile.info('Latitude reference: ' + lat_ref)
            logFile.info('Latitude: ' + lat)
            logFile.info('Longitude reference: ' + lon_ref)
            logFile.info('Longitude: ' + lon)
            logConsole.error('GPS-Converter has crushed.')

    # Return positive ir negative longitude/latitude from exifread's ifdtag
    lat = -(idf_tag_to_coordinate(lat)) if lat_ref == 'S' else idf_tag_to_coordinate(lat)
    lon = -(idf_tag_to_coordinate(lon)) if lon_ref == 'W' else idf_tag_to_coordinate(lon)
    return [lat, lon]


# Save camera info to database to collect statistics
def save_camera_info(cb, cm, lb, lm):
    db = db_connector.connect()
    if not db:
        logFile.warning('Can\'t connect to db.')
        logConsole.warning('Can\'t connect to db.')
        return
    cursor = db.cursor()

    for data in (cb, cm, lb, lm):
        query = 'SELECT id FROM statistics WHERE camera_brand = "{}"'.format(data)
        row = cursor.execute(query)
        if row:
            pass


def read_exif(image):

    answer = []
    exif = exifread.process_file(image, details=False)
    if len(exif.keys()) < 1:
        logFile.info('This picture doesn\'t contain EXIF.')
        logConsole.info('This picture doesn\'t contain EXIF.')
        return False

    answer.extend(exif_to_dd(exif))

    # Get necessary tags from EXIF data

    date_time = exif.get('EXIF DateTimeOriginal', None)
    camera_brand = exif.get('Image Make', None)
    camera_model = exif.get('Image Model', None)
    lens_brand = exif.get('EXIF LensMake', None)
    lens_model = exif.get('EXIF LensModel', None)

    if not any([date_time, camera_brand, camera_model, lens_brand, lens_model]):
        return False  # Means that there is actually no any date of our interest

    date_time_str = lang['camera_info'][0] + ': ' + str(date_time) + '\n' if date_time is not None else None
    camera_brand_str = lang['camera_info'][1] + ': ' + str(camera_brand) + '\n' if camera_brand is not None else None
    camera_model_str = lang['camera_info'][2] + ': ' + str(camera_model) + '\n' if camera_model is not None else None
    lens_brand_str = lang['camera_info'][3] + ': ' + str(lens_brand) + '\n' if lens_brand is not None else None
    lens_model_str = lang['camera_info'][4] + ': ' + str(lens_model) + '\n' if lens_model is not None else None

    # Haven't done it yet completely
    # save_camera_info(camera_brand_str, camera_model_str, lens_brand_str, lens_model_str)

    info_about_shot = ''
    for item in [date_time_str, camera_brand_str, camera_model_str, lens_brand_str, lens_model_str]:
        if item is not None:
            info_about_shot += item

    answer.append(info_about_shot)
    return answer


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    bot.send_message(message.chat.id, lang['photo_prcs'])
    log_msg = ('Name: {} Last name: {} Nickname: {} ID: {} sent photo as a file.'.format(message.from_user.first_name,
                                                                                         message.from_user.last_name,
                                                                                         message.from_user.username,
                                                                                         message.from_user.id))

    logFile.info(log_msg)
    logConsole.info(log_msg)

    # get image
    file_id = bot.get_file(message.document.file_id)
    # Get temporary link to photo that user has sent to bot
    file_path = file_id.file_path
    # Get photo that got telegram bot from user
    r = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(config.token, file_path))
    user_file = BytesIO(r.content)  # Get file-like object of user's photo

    # Get coordinates
    answer = read_exif(user_file)
    if not answer:
        bot.send_message(message.chat.id, lang['no_exif'])
    elif len(answer) == 3:
        # Sent info back to user
        lat, lon = answer[0], answer[1]
        bot.send_location(message.chat.id, lat, lon, live_period=None)
        bot.send_message(message.chat.id, text=answer[2])
        logFile.info('Success')
        logConsole.info('Success')
    else:
        bot.send_message(message.chat.id, answer[0] + '\n' + answer[1])


error_counter = 0
while True:
    if error_counter == 30:
        logConsole.error('Emergency stop due to loop of polling exceptions')
        exit()
    try:
        if __name__ == '__main__':
            bot.polling(none_stop=True)  # Keep bot receiving messages
    except:
        logFile.error('Freaking polling!')
        logConsole.error('Freaking polling!')
        error_counter += 1

# if __name__ == '__main__':
#     bot.polling(none_stop=True)  # Keep bot receiving messages
