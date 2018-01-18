#!python3
# -*- coding: utf-8 -*-

# Small bot for Telegram that receive your photo and return you map where it was taken.
# Written by Aleksandr Mikheev.
# https://github.com/RandyRomero/map_returning_bot

# TODO Make answers of bot depend on language of user

import config
import telebot
import exifread
import requests
from io import BytesIO
from datetime import datetime
import handle_logs
from pprint import pprint

logFile, logConsole = handle_logs.set_loggers()  # set up logging via my module

bot = telebot.TeleBot(config.token)


@bot.message_handler(content_types=['text'])  # Decorator to handle text messages
def repeat_all_messages(message):
    # Function that echos all users messages
    text = ('Я не умею разговаривать, но, если ты пришлёшь мне фотографию, я отправлю тебе карту с указанием, где эта '
            'фотография была сделана.')
    bot.send_message(message.chat.id, text)

    print('{}: user {} a.k.a. {} sent text message.'.format(datetime.fromtimestamp(message.date),
                                                            message.from_user.first_name,
                                                            message.from_user.username,
                                                            message.from_user.last_name))


def exif_to_dd(value):
    # Convert exif gps to format that accepts Telegram (and Google Maps for example)

    lat_ref = str(value[0])
    lat = value[1]
    lon_ref = str(value[2])
    lon = value[3]

    def idf_tag_to_coordinate(tag):
        # convert ifdtag from exifread module to decimal degree format of coordinate
        tag = str(tag).replace('[', '').replace(']', '').split(',')
        tag[2] = int(tag[2].split('/')[0]) / int(tag[2].split('/')[1])
        return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600

    # Return positive ir negative longitude/latitude from exifread's ifdtag
    lat = -(idf_tag_to_coordinate(lat)) if lat_ref == 'S' else idf_tag_to_coordinate(lat)
    lon = -(idf_tag_to_coordinate(lon)) if lon_ref == 'W' else idf_tag_to_coordinate(lon)

    return lat, lon


def read_exif(image):

    answer = []
    tags = exifread.process_file(image, details=False)
    if len(tags.keys()) < 1:
        answer.append('The is no EXIF in this file.')
        return answer

    try:
        raw_coordinates = [tags['GPS GPSLatitudeRef'],
                           tags['GPS GPSLatitude'],
                           tags['GPS GPSLongitudeRef'],
                           tags['GPS GPSLongitude']]

        answer.append(True)
        lat, lon = exif_to_dd(raw_coordinates)
        answer.extend([lat, lon])
        return answer

    except KeyError:
        answer.append(False)
        answer.append('Это фотография не имеет GPS-данных. Попробуй другую')
        print('This picture doesn\'t contain GPS coordinates.')
        return answer


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    print('{}: user {} a.k.a. {} sent photo as a file.'.format(datetime.fromtimestamp(message.date),
                                                               message.from_user.first_name,
                                                               message.from_user.username,
                                                               message.from_user.last_name))
    # get image
    file_id = bot.get_file(message.document.file_id)
    # Get temporary link to photo that user has sent to bot
    file_path = file_id.file_path
    # Get photo that got telegram bot from user
    r = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(config.token, file_path))
    user_file = BytesIO(r.content)  # Get file-like object of user's photo

    # Get coordinates
    answer = read_exif(user_file)
    if answer[0]:
        # Sent info back to user
        lat, lon = answer[1], answer[2]
        bot.send_location(message.chat.id, lat, lon, live_period=None)
    else:
        bot.send_message(message.chat.id, answer[1])


if __name__ == '__main__':  # Keep bot receiving messages
    bot.polling(none_stop=True)
