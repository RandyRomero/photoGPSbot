import exifread
from geopy.geocoders import Nominatim
from collections import namedtuple

import config
from photogpsbot import bot, log, db, user_language, send_last_logs


class ImageData:
    def __init__(self,
                 date_time=None,
                 camera=None,
                 lens=None,
                 address=None,
                 country=None
                 ):

        self.date_time = date_time
        self.camera = camera
        self.lens = lens
        self.address = address
        self.country = country


class RawImageData():
    def __init__(self,
                 date_time=None,
                 latitude_reference=None,
                 raw_latitude=None,
                 longitude_reference=None,
                 raw_longitude=None,
                 camera_brand=None,
                 camera_model=None,
                 lens_brand=None,
                 lens_model=None,
                 ):

        self.date_time = date_time
        self.latitude_reference = latitude_reference
        self.raw_latitude = raw_latitude
        self.longitude_reference = longitude_reference
        self.raw_longitude = raw_longitude
        self.camera_brand = camera_brand
        self.camera_model = camera_model
        self.lens_brand = lens_brand
        self.lens_model = lens_model


class ImageHandler:

    def __init__(self, file):
        self.file = file
        self.raw_data = None

    @staticmethod
    def _get_raw_data_from_file(file):
        exif = exifread.process_file(file, details=False)
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

        try:  # Extract coordinates from EXIF
            latitude_reference = str(exif['GPS GPSLatitudeRef'])
            raw_latitude = exif['GPS GPSLatitude']
            longitude_reference = str(exif['GPS GPSLongitudeRef'])
            raw_longitude = exif['GPS GPSLongitude']

        except KeyError:
            log.info("This picture doesn't contain coordinates.")

            return RawImageData(date_time=date_time,
                                camera_brand=camera_brand,
                                camera_model=camera_model,
                                lens_brand=lens_brand,
                                lens_model=lens_model)

        return RawImageData(
            date_time=date_time,
            latitude_reference=latitude_reference,
            raw_latitude=raw_latitude,
            longitude_reference=longitude_reference,
            raw_longitude=raw_longitude,
            camera_brand=camera_brand,
            camera_model=camera_model,
            lens_brand=lens_brand,
            lens_model=lens_model
            )

    @staticmethod
    def _dedupe_string(string):
        splitted_string = string.split(' ')
        deduped_string = ''
        for x in splitted_string:
            if x not in deduped_string:
                deduped_string += x + ' '
        return deduped_string.rstrip()

    @staticmethod
    def _check_camera_tags(tags):
        """
        Function that convert stupid code name of a smartphone or camera
        from EXIF to meaningful one by looking a collation in a special MySQL
        table For example instead of just Nikon there can be
        NIKON CORPORATION in EXIF

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

    @staticmethod
    def _get_dd_coordinate(angular_distance, reference):
        # Convert ifdtag from exifread module to decimal degree format
        # of coordinate
        tag = (str(angular_distance).
               replace('[', '').replace(']', '').split(','))

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

        if reference in 'WS':
            return -(int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600)

        return int(tag[0]) + int(tag[1]) / 60 + tag[2] / 3600

    def _convert_coordinates(self, raw_data):
        """
        # Convert GPS coordinates from format in which they are stored in
        EXIF of photo to format that accepts Telegram (and Google Maps for
        example)

        :param data: EXIF data extracted from photo
        :param chat_id: user id
        :return: either floats that represents longitude and latitude or
        string with error message dedicated to user
        """

        # Return positive or negative longitude/latitude from exifread's ifdtag

        latitude = self._get_dd_coordinate(raw_data.latitude_reference,
                                           raw_data.raw_latitude)
        longitude = self._get_dd_coordinate(raw_data.longitude_reference,
                                            raw_data.raw_longitude)

        if latitude is False or longitude is False:
            log.error('Cannot read coordinates of this photo.')
            raw_coordinates = (f'Latitude reference: '
                               f'{raw_data.latitude_reference}\n'
                               f'Raw latitude: {raw_data.raw_latitude}.\n'
                               f'Longitude reference: '
                               f'{raw_data.longitude_reference} '
                               f'Raw longitude: {raw_data.raw_longitude}.\n')
            log.info(raw_coordinates)

        return latitude, longitude

    def _get_address(latitude, longitude):

        """
         # Get address as a string by coordinates from photo that user sent
         to bot
        :param latitude:
        :param longitude:
        :param lang: preferred user language
        :return: address as a string where photo was taken; name of
        country in English and Russian to keep statistics
        of the most popular countries among users of the bot
        """

        address = {}
        country = {}
        coordinates = "{}, {}".format(latitude, longitude)
        log.debug('Getting address from coordinates %s...', coordinates)
        geolocator = Nominatim()

        try:
            # Get name of the country in English and Russian language
            location = geolocator.reverse(coordinates, language='en')
            address['en-US'] = location.address
            country['en-US'] = location.raw['address']['country']

            location2 = geolocator.reverse(coordinates, language='ru')
            address['ru-RU'] = location2.address
            country['ru-RU'] = location2.raw['address']['country']
            return address, country

        except Exception as e:
            log.error('Getting address has failed!')
            log.error(e)
            send_last_logs()
            return False

    def _convert_data(self, raw_data):
        date_time = (str(raw_data.date_time) if raw_data.date_time else None)

        # Merge a brand and model together
        camera_string = f'{raw_data.camera_brand} {raw_data.camera_model}'
        lens_string = f'{raw_data.lens_brand} {raw_data.lens_model}'

        # Get rid of repetitive words
        camera = (self._dedupe_string(camera_string)
                  if camera_string != ' ' else None)
        lens = (self._dedupe_string(lens_string)
                if lens_string != ' ' else None)

        camera, lens = self._check_camera_tags([camera, lens])

        if raw_data.longitude_reference:
            coordinates = self._convert_coordinates(raw_data)
            address, country = self._get_address(coordinates)
        else:
            address = None
            country = None

        return date_time, camera, lens, address, country

    def _save_user_query_info(self, image_data):
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
        camera_name, lens_name = image_data.camera, image_data.lens
        camera_name = 'NULL' if not camera_name else f'"{camera_name}"'

        lens_name = 'NULL' if not lens_name else f'"{lens_name}"'
        chat_id = message.chat.id
        msg = message.from_user
        first_name = ('NULL' if not msg.first_name
                      else '{0}{1}{0}'.format('"', msg.first_name))
        last_name = ('NULL' if not msg.last_name
                     else '{0}{1}{0}'.format('"', msg.last_name))
        username = ('NULL' if not msg.username
                    else '{0}{1}{0}'.format('"', msg.username))
        if not image_data.country:
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

    def get_info(self):

        # Read data from photo and prepare answer for user
        # with location and etc.

        raw_data = self._get_raw_data_from_file(self.file)
        image_data = ImageData(self._convert_data(raw_data))
        self._save_user_query_info(image_data)


        # Sent to user only info about camera because there is no gps
        # coordinates in his photo
        user_msg = '{}\n{}'.format(answer[0], answer[1])
        bot.reply_to(message, user_msg, parse_mode='Markdown')
        log.info('Sent only EXIF data back to Name: %s Last name: %s '
                 'Nickname: %s ID: %d', msg.first_name, msg.last_name,
                 msg.username, msg.id)

    def read_exif(self, image, message):
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
            lang = 'ru' if user_language.get(chat_id) == 'ru-RU' else 'en'
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


        answer.append(info_about_shot)

        return [answer, camera_info, country]


    def _convert_data(self, raw_data):
        self.image_data.date_time = (str(raw_data.date_time) if
                                     raw_data.date_time else None)

        # Merge a brand and model together
        camera_string = f'{raw_data.camera_brand} {raw_data.camera_model}'
        lens_string = f'{raw_data.lens_brand} {raw_data.lens_model}'

        # Get rid of repetitive words
        camera = (self._dedupe_string(camera_string)
                  if camera_string != ' ' else None)
        lens = (self._dedupe_string(lens_string)
                if lens_string != ' ' else None)

        result = self._check_camera_tags([camera, lens])
        self.image_data.camera, self.image_data.lens = result

        if raw_data.longitude_reference:
            coordinates = self._convert_coordinates(raw_data)
            address, country = self._get_address(coordinates)
            self.image_data.address = address
            self.image_data.country = country
        else:
            self.image_data.address = ''
            self.image_data.country = 'NULL'