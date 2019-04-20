from dataclasses import dataclass
from typing import Dict

import exifread
from exifread.classes import IfdTag
from geopy.geocoders import Nominatim

from photogpsbot import bot, log, db, User


class InvalidCoordinates(Exception):
    """
    Coordinates have invalid format
    """


class NoCoordinates(Exception):
    """
    There is no location info
    """


class NoEXIF(Exception):
    """
    Means that there is no EXIF within the photo at all

    """


class NoData(Exception):
    """
    Means that there is actually no any data of our interest within the picture

    """


@dataclass
class ImageData:
    """
    A class to store info about a photo from user.
    """
    user: User
    date_time: str = None
    camera: str = None
    lens: str = None
    address: str = None
    country: Dict[str, str] = None
    longitude: float = None
    latitude: float = None


@dataclass
class RawImageData:
    """
    Raw data from photo that is still have to be converted in order to be used.
    """
    user: User
    date_time: str = None
    camera_brand: str = None
    camera_model: str = None
    lens_brand: str = None
    lens_model: str = None
    latitude_reference: str = None
    raw_latitude: IfdTag = None
    longitude_reference: str = None
    raw_longitude: IfdTag = None


class ImageHandler:

    def __init__(self, user, file):
        self.user = user
        self.file = file
        self.raw_data = None

    def _get_raw_data(self, file):
        """
        Get name of the camera and lens, the date when the photo was taken
        and raw coordinates (which later will be converted)
        :param file: byte sting with an image
        :return: RawImageData object with raw info from the photo
        """
        # Get data from the exif of the photo via external library
        exif = exifread.process_file(file, details=False)
        if not len(exif.keys()):
            reason = "This picture doesn't contain EXIF."
            log.info(reason)
            raise NoEXIF(reason)

        # Get info about camera ang lend from EXIF
        date_time = exif.get('EXIF DateTimeOriginal', None)
        date_time = str(date_time) if date_time else None
        camera_brand = str(exif.get('Image Make', ''))
        camera_model = str(exif.get('Image Model', ''))
        lens_brand = str(exif.get('EXIF LensMake', ''))
        lens_model = str(exif.get('EXIF LensModel', ''))

        if not any([date_time, camera_brand, camera_model, lens_brand,
                    lens_model]):
            # Means that there is actually no any data of our interest
            reason = 'There is no data of interest in this photo'
            log.info(reason)
            raise NoData(reason)

        try:  # Extract coordinates from EXIF
            latitude_reference = str(exif['GPS GPSLatitudeRef'])
            raw_latitude = exif['GPS GPSLatitude']
            longitude_reference = str(exif['GPS GPSLongitudeRef'])
            raw_longitude = exif['GPS GPSLongitude']

        except KeyError:
            log.info("This picture doesn't contain coordinates.")
            # returning info about the photo without coordinates
            return (self.user, date_time, camera_brand, camera_model,
                    lens_brand, lens_model)
        else:
            # returning info about the photo with its coordinates
            return (self.user, date_time, camera_brand, camera_model,
                    lens_brand, lens_model, latitude_reference, raw_latitude,
                    longitude_reference, raw_longitude)

    @staticmethod
    def _dedupe_string(string):
        """
        Get rid of all repetitive words in a string
        :param string: string with camera or lens names
        :return: same string without repetitive words
        """

        deduped_string = ''

        for x in string.split(' '):
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
        """
         Convert coordinates from format in which they are typically written
         in EXIF to decimal degrees - format that Telegram or Google Map
         understand. Google coordinates, EXIF and decimals degrees if you
         need to understand what is going on here

         :param angular_distance: ifdTag object from the exifread module -
         it contains a raw coordinate - either longitude or latitude
         :param reference:
          :return: a coordinate in decimal degrees format
         """
        ag = angular_distance
        degrees = ag.values[0].num / ag.values[0].den
        minutes = (ag.values[1].num / ag.values[1].den) / 60
        seconds = (ag.values[2].num / ag.values[2].den) / 3600

        if reference in 'WS':
            return -(degrees + minutes + seconds)

        return degrees + minutes + seconds

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

        try:
            latitude = self._get_dd_coordinate(raw_data.latitude_reference,
                                               raw_data.raw_latitude)
            longitude = self._get_dd_coordinate(raw_data.longitude_reference,
                                                raw_data.raw_longitude)

        except Exception as e:
            # todo also find out the error in case there is no coordinates in
            #  raw_data
            log.error(e)
            log.error('Cannot read coordinates of this photo.')
            raw_coordinates = (f'Latitude reference: '
                               f'{raw_data.latitude_reference}\n'
                               f'Raw latitude: {raw_data.raw_latitude}.\n'
                               f'Longitude reference: '
                               f'{raw_data.longitude_reference} '
                               f'Raw longitude: {raw_data.raw_longitude}.\n')
            log.info(raw_coordinates)
            raise InvalidCoordinates

        else:
            return longitude, latitude

    @staticmethod
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
            bot.send_last_logs()
            raise

    def _convert_data(self, raw_data):
        date_time = (str(raw_data.date_time) if raw_data.date_time else None)

        # Merge a brand and model together
        camera = f'{raw_data.camera_brand} {raw_data.camera_model}'
        lens = f'{raw_data.lens_brand} {raw_data.lens_model}'

        # Get rid of repetitive words
        camera = (self._dedupe_string(camera) if camera != ' ' else None)
        lens = (self._dedupe_string(lens) if lens != ' ' else None)

        camera, lens = self._check_camera_tags([camera, lens])

        try:
            longitude, latitude = self._convert_coordinates(raw_data)
        except (InvalidCoordinates, NoCoordinates):
            address = country = longitude = latitude = None
        else:
            try:
                address, country = self._get_address(longitude, latitude)
            except Exception as e:
                log.warning(e)
                address = country = None

        return date_time, camera, lens, address, country, longitude, latitude

    def get_image_info(self):
        """
        Read data from photo and prepare answer for user
        with location and etc.
        """
        raw_data = RawImageData(*self._get_raw_data(self.file))
        image_data = ImageData(*self._convert_data(raw_data))

        return image_data
