#!python3
# -*- coding: utf-8 -*-

language_ru = {
    'dont_speak': ('Я не умею разговаривать, но, если ты пришлёшь мне фотографию, '
                   'я отправлю тебе карту с указанием, где эта фотография была сделана, дату съёмки и информацию'
                   'о камере.'),
    'as_file': ('Прости, но фотографию нужно отправлять, как файл. Если отправлять её просто как фото, '
                'то Telegram сожмёт её и выбросит данные о местоположении, и я не смогу тебе его прислать.'),
    'no_gps': 'Это фотография не имеет GPS-данных. Попробуй другую.',
    'bad_gps': 'Не могу распознать формат GPS. Напиши @SavageRandy, вдруг починит.',
    'no_exif': 'В этой фотографии нет EXIF-данных.',
    'photo_prcs': 'Поймал! Обрабатываю...',
    'camera_info': ['Дата съёмки: ', 'Камера: ', 'Объектив: ']
}

language_en = {
    'dont_speak': ('I cannot speak, but if you send me a photo (as a file), I will send you back the location'
                   ' where it was taken, time of shooting and camera info.'),
    'as_file': ('Sorry, but it would be better if you send your photo as a file. If you send it just as a photo, '
                'Telegram will get rid of location and data in order to compress the photo.'),
    'no_gps': 'This photo does not have info about location. Try another one.',
    'bad_gps': 'Cannot read GPS from this photo. Maybe @SavageRandy can help you.',
    'no_exif': 'This photo does not contain any data. Maybe you have another one?',
    'photo_prcs': 'Wait a sec... *sounds of heavy machinery*',
    'camera_info': ['Date', 'Camera brand: ', 'Lens brand: ']
}