#!python3
# -*- coding: utf-8 -*-

# Small bot for Telegram that receive your photo and return you map where it was taken.
# Written by Aleksandr Mikheev.
# https://github.com/RandyRomero/map_returning_bot

import config
import telebot
import exifread
import requests
from io import BytesIO
from datetime import datetime
import handle_logs

logFile, logConsole = handle_logs.set_loggers()  # set up logging via my module

bot = telebot.TeleBot(config.token)


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def answer_text_message(message):
    # Function that echos all users messages
    text = ('Я не умею разговаривать, но, если ты пришлёшь мне фотографию, я отправлю тебе карту с указанием, где эта '
            'фотография была сделана.')
    bot.send_message(message.chat.id, text)
    log_msg = ('{}: user {} a.k.a. {} sent text message.'.format(datetime.fromtimestamp(message.date),
                                                                 message.from_user.first_name,
                                                                 message.from_user.username,
                                                                 message.from_user.last_name))
    logFile.info(log_msg)
    logConsole.info(log_msg)


@bot.message_handler(content_types=['photo'])
def answer_photo_message(message):
    text = ('Прости, но фотографию нужно отправлять, как файл. Если отправлять её просто как фото, то серверы Telegram'
            ' сожмут её и выбросят данные о местоположении, и я не смогу тебе его прислать.')
    bot.send_message(message.chat.id, text)
    log_message = ('{}: user {} a.k.a. {} sent photo as a photo.'.format(datetime.fromtimestamp(message.date),
                                                                         message.from_user.first_name,
                                                                         message.from_user.username,
                                                                         message.from_user.last_name))
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

        return ['Это фотография не имеет GPS-данных. Попробуй другую.']
        # TODO Save exif of photo if converter catch an error trying to convert gps data

    def idf_tag_to_coordinate(tag):
        # convert ifdtag from exifread module to decimal degree format of coordinate
        tag = str(tag).replace('[', '').replace(']', '').split(',')
        tag[2] = int(tag[2].split('/')[0]) / int(tag[2].split('/')[1])
        return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600

    # Return positive ir negative longitude/latitude from exifread's ifdtag
    lat = -(idf_tag_to_coordinate(lat)) if lat_ref == 'S' else idf_tag_to_coordinate(lat)
    lon = -(idf_tag_to_coordinate(lon)) if lon_ref == 'W' else idf_tag_to_coordinate(lon)

    return [lat, lon]


def read_exif(image):

    answer = []
    exif = exifread.process_file(image, details=False)
    if len(exif.keys()) < 1:
        answer.append(False)
        answer.append('В этой фотографии нет EXIF-данных.')
        logFile.info('This picture doesn\'t contain EXIF.')
        logConsole.info('This picture doesn\'t contain EXIF.')
        return answer

    answer.extend(exif_to_dd(exif))

    # Get necessary tags from EXIF data

    date_time = exif.get('EXIF DateTimeOriginal', None)
    camera_brand = exif.get('Image Make', None)
    camera_model = exif.get('Image Model', None)
    lens_brand = exif.get('EXIF LensMake', None)
    lens_model = exif.get('EXIF LensModel', None)

    date_time_str = 'Дата съёмки: ' + str(date_time) + '\n' if date_time is not None else None
    camera_brand_str = 'Марка камеры: ' + str(camera_brand) + '\n' if camera_brand is not None else None
    camera_model_str = 'Модель камеры: ' + str(camera_model) + '\n' if camera_model is not None else None
    lens_brand_str = 'Марка объектива: ' + str(lens_brand) + '\n' if lens_brand is not None else None
    lens_model_str = 'Модель объектива: ' + str(lens_model) + '\n' if lens_model is not None else None

    info_about_shot = ''
    for item in [date_time_str, camera_brand_str, camera_model_str, lens_brand_str, lens_model_str]:
        if item is not None:
            info_about_shot += item

    answer.append(info_about_shot)
    return answer


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    log_msg = ('{}: user {} a.k.a. {} sent photo as a file.'.format(datetime.fromtimestamp(message.date),
                                                                    message.from_user.first_name,
                                                                    message.from_user.username,
                                                                    message.from_user.last_name))

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
    if len(answer) == 3:
        # Sent info back to user
        lat, lon = answer[0], answer[1]
        bot.send_location(message.chat.id, lat, lon, live_period=None)
        bot.send_message(message.chat.id, text=answer[2])
        logFile.info('Success')
        logConsole.info('Success')
    else:
        bot.send_message(message.chat.id, answer[0] + '\n' + answer[1])


while True:
    try:
        if __name__ == '__main__':
            bot.polling(none_stop=True)  # Keep bot receiving messages
    except TypeError:  # I hope it is the right exception
        logFile.error('Freaking polling!')
        logConsole.error('Freaking polling!')
