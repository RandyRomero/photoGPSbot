#!python3
# -*- coding: utf-8 -*-

# Small bot for Telegram that receive your photo and return you map where it was taken.
# Written by Aleksandr Mikheev.
# https://github.com/RandyRomero/map_returning_bot

import config
import telebot
import exifread
import requests
from PIL import Image
from io import BytesIO

# TeleBot encapsulates all API calls in a single class. It provides functions 
# such as # send_xyz (send_message, send_document etc.) and several ways to 
# listen for incoming messages.
bot = telebot.TeleBot(config.token)


# @bot.message_handler(content_types=['text'])  # Decorator to handle text messages
# def repeat_all_messages(message):
#     # Function that echos all users messages
#
#     # Send_message  - function of TeleBot
#     # Message is an object of telegram API
#     # Chat is a conversation message belongs to
#     # id - unique identifier for this chat.
#     # text -  for text messages, the actual UTF-8 text of the message, 0-4096 characters.
#     bot.send_message(message.chat.id, message.text)


@bot.message_handler(content_types=['document'])  # receive file
def handle_image(message):
    # get image
    # get coordinates

    def read_exif(image):
        # with open(file, 'rb') as image:
        tags = exifread.process_file(image, details=False)
        if len(tags.keys()) < 1:
            print('The is no EXIF in this file.')
            exit()

        try:
            raw_coordinates = [tags['GPS GPSLatitudeRef'],
                               tags['GPS GPSLatitude'],
                               tags['GPS GPSLongitudeRef'],
                               tags['GPS GPSLongitude']]

            exif_to_dd(raw_coordinates)

        except KeyError:
            bot.send_message(message.chat.id, "Эта фотография не имеет GPS-координат. Попробуй другую.")
            print('This picture doesn\'t contain GPS coordinates.')

    def exif_to_dd(value):
        lat_ref = str(value[0])
        lat = value[1]
        lon_ref = str(value[2])
        lon = value[3]

        def idf_tag_to_coordinate(tag):
            # convert ifdtag from exifread module to decimal degree coordinate
            tag = str(tag).replace('[', '').replace(']', '').split(',')
            tag[2] = int(tag[2].split('/')[0]) / int(tag[2].split('/')[1])
            return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600

        # Return positive ir negative longitude/latitude from exifread's ifdtag
        lat = -(idf_tag_to_coordinate(lat)) if lat_ref == 'S' else idf_tag_to_coordinate(lat)
        lon = -(idf_tag_to_coordinate(lon)) if lon_ref == 'W' else idf_tag_to_coordinate(lon)

        print('GPS coordinates in decimal degrees format:')

        bot.send_location(message.chat.id, lat, lon, live_period=None)

    file_id = bot.get_file(message.document.file_id)
    file_path = file_id.file_path
    r = requests.get('https://api.telegram.org/file/bot{0}/{1}'.format(config.token, file_path))
    # print(file)
    user_file = BytesIO(r.content)
    read_exif(user_file)


if __name__ == '__main__':
    bot.polling(none_stop=True)
