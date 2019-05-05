from dataclasses import dataclass, field
from typing import Dict, Tuple, List
from io import BytesIO
from typing import Optional

import exifread  # type: ignore
from exifread.classes import IfdTag  # type: ignore
from geopy.geocoders import Nominatim  # type: ignore

from photogpsbot import log, db, User


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
    A class to store info about a photo from a user.
    """
    user: User
    date_time: Optional[str] = None
    camera: Optional[str] = None
    lens: Optional[str] = None
    address: Optional[Dict[str, str]] = None
    country: Optional[Dict[str, str]] = None
    latitude: float = 0
    longitude: float = 0


@dataclass
class RawImageData:
    """
    Raw data from photo that is still have to be converted in order to be used.
    """
    user: User
    date_time: Optional[str] = None
    camera_brand: Optional[str] = None
    camera_model: Optional[str] = None
    lens_brand: Optional[str] = None
    lens_model: Optional[str] = None
    latitude_reference: Optional[str] = None
    raw_latitude: Optional[IfdTag] = None
    longitude_reference: Optional[str] = None
    raw_longitude: Optional[IfdTag] = None


class ImageHandler:

    def __init__(self, user: User, file: BytesIO) -> None:
        self.user = user
        self.file = file

    def _get_raw_data(self, file: BytesIO) -> RawImageData:
        """
        Gets raw information out of an image

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
            lat_ref = exif['GPS GPSLatitudeRef']
            lon_ref = exif['GPS GPSLongitudeRef']

            # prevent having ifdtag instead of a plane None
            latitude_reference = str(lat_ref) if lat_ref.values else None
            longitude_reference = str(lon_ref) if lon_ref.values else None

            raw_latitude = exif['GPS GPSLatitude']
            raw_longitude = exif['GPS GPSLongitude']

        except (KeyError, AttributeError):
            log.info("This picture doesn't contain coordinates.")
            # returning info about the photo without coordinates
            return RawImageData(self.user, date_time, camera_brand,
                                camera_model, lens_brand, lens_model)
        else:
            # returning info about the photo with its coordinates
            return RawImageData(self.user, date_time, camera_brand,
                                camera_model, lens_brand, lens_model,
                                latitude_reference, raw_latitude,
                                longitude_reference, raw_longitude)

    @staticmethod
    def _dedupe_string(string: str) -> str:
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
    def _check_camera_tags(*tags: str) -> List[str]:
        """
        Converts camera and lens name to proper ones

        Function that convert stupid code name of a smartphone or a camera
        from EXIF to a meaningful one by looking a collation in a special MySQL
        table For example instead of just Nikon there can be
        NIKON CORPORATION in EXIF

        :param tags: a tuple with a name of a camera and lens from EXIF
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
                         'WHERE wrong_tag=%s')
                parameters = tag,
                cursor = db.execute_query(query, parameters)
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
    def _get_dd_coordinate(angular_distance: IfdTag,
                           reference: Optional[str]) -> float:
        """
        Converts one coordinate to the common format

        Convert coordinates from format in which they are typically written
        in EXIF to decimal degrees - format that Telegram and Google Map
        understand. Google coordinates, EXIF and decimals degrees if you
        need to understand what is going on here

        :param angular_distance: ifdTag object from the exifread module -
        it contains a raw coordinate - either longitude or latitude
        :param reference: to what half of Earth a coordinates belongs to
        :return: a coordinate in decimal degrees format
        """
        ag = angular_distance
        degrees = ag.values[0].num / ag.values[0].den
        minutes = (ag.values[1].num / ag.values[1].den) / 60
        seconds = (ag.values[2].num / ag.values[2].den) / 3600

        if reference in 'WS':
            return -(degrees + minutes + seconds)

        return degrees + minutes + seconds

    def _convert_coordinates(self, raw_data: RawImageData) -> Tuple[float,
                                                                    float]:
        """
        Converts coordinates to the common format

        Convert GPS coordinates from format in which they are stored in
        EXIF of photo to format that accepts Telegram (and Google Maps for
        example)

        :param raw_data: info about an image with its coordinates
        :return: tuple of floats that represents longitude and latitude
        """

        try:
            latitude = self._get_dd_coordinate(raw_data.raw_latitude,
                                               raw_data.latitude_reference)
            longitude = self._get_dd_coordinate(raw_data.raw_longitude,
                                                raw_data.longitude_reference)

        except (AttributeError, TypeError) as e:
            log.info(e)
            log.info("The photo does not contain proper coordinates")
            raise NoCoordinates

        except Exception as e:
            log.info(e)
            log.info('Cannot read coordinates of this photo.')
            raw_coordinates = (f'Latitude reference: '
                               f'{raw_data.latitude_reference}\n'
                               f'Raw latitude: {raw_data.raw_latitude}.\n'
                               f'Longitude reference: '
                               f'{raw_data.longitude_reference}\n'
                               f'Raw longitude: {raw_data.raw_longitude}.\n')
            log.info(raw_coordinates)
            raise InvalidCoordinates

        return latitude, longitude

    def _get_address(self, latitude: float, longitude: float) \
            -> Tuple[Dict[str, str], Dict[str, str]]:

        """
         # Get address as a string by coordinates from photo that user sent
         to bot

        :param latitude: latitude from a photo as a float
        :param longitude: longitude rom a photo as a float
        :return: address as a string where photo was taken; name of
        country in English and Russian to keep statistics
        of the most popular countries among users of the bot
        """

        address = {}
        country = {}
        coordinates = f"{latitude}, {longitude}"
        log.debug('Getting address from coordinates %s...', coordinates)
        geolocator = Nominatim()
        lang = self.user.language

        try:
            # Get name of the country in English and Russian language
            location_en = geolocator.reverse(coordinates, language='en')
            address['en-US'] = location_en.address
            country['en-US'] = location_en.raw['address']['country']

            location_ru = geolocator.reverse(coordinates, language='ru')
            address['ru-RU'] = location_ru.address
            country['ru-RU'] = location_ru.raw['address']['country']

            address = address[lang]
            return address, country

        except Exception as e:
            log.error(e)
            log.error('Getting address has failed!')
            raise

    def _convert_data(self, raw_data: RawImageData) -> ImageData:
        """
        Cleans data from a picture that a user sends

        :param raw_data: object with raw info about a picture
        :return: object with formatted info about a picture
        """

        date_time = (str(raw_data.date_time) if raw_data.date_time else None)

        # Merge a brand and model together
        camera = f'{raw_data.camera_brand} {raw_data.camera_model}'
        lens = f'{raw_data.lens_brand} {raw_data.lens_model}'

        # Get rid of repetitive words
        camera = (self._dedupe_string(camera) if camera != ' ' else None)
        lens = (self._dedupe_string(lens) if lens != ' ' else None)

        camera, lens = self._check_camera_tags(camera, lens)

        try:
            latitude, longitude = self._convert_coordinates(raw_data)
        except (InvalidCoordinates, NoCoordinates):
            address = country = latitude = longitude = None
        else:
            try:
                address, country = self._get_address(latitude, longitude)
            except Exception as e:
                log.warning(e)
                address = country = None

        return ImageData(self.user, date_time, camera, lens, address, country,
                         latitude, longitude)

    def get_image_info(self) -> ImageData:
        """
        Read data from photo and prepare answer for user
        with location and etc.

        :return: object with formatted info about a picture
        """
        raw_data = self._get_raw_data(self.file)
        image_data = self._convert_data(raw_data)

        return image_data
