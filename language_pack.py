#!python3
# -*- coding: utf-8 -*-

lang_msgs = {
    'ru-RU': {
        'menu_header': 'Отправь фото или выбери пункт:',
        'switch_lang_success': 'Теперь я говорю по-русски!',
        'switch_lang_failure': 'Не удалось сменить язык. Попробуйте позже.',
        'dont_speak': ('Я не умею разговаривать, но, если ты пришлёшь мне фотографию, '
                       'я отправлю тебе карту с указанием, где эта фотография была сделана, дату съёмки и информацию'
                       ' о камере.'),
        'as_file': ('Прости, но фотографию нужно отправлять, как файл. Если отправлять её просто как фото, '
                    'то Telegram сожмёт её и выбросит данные о местоположении, и я не смогу тебе его прислать.'),
        'no_gps': 'Это фотография не имеет GPS-данных. Попробуй другую.',
        'bad_gps': 'Не могу распознать формат GPS. Напиши @SavageRandy, вдруг починит.',
        'no_exif': 'В этой фотографии нет EXIF-данных.',
        'photo_prcs': 'Поймал! Обрабатываю...',
        'camera_info': ['Дата съёмки: ', 'Камера: ', 'Объектив: '],
        'top_cams': 'Самые популярные смартфоны/камеры пользователей @photogpsbot',
        'top_lens': 'Самые популярные объективы пользователей @photogpsbot',
        'oops': 'Упс! Эта фича пока еще в разработке. Но, если ты пришлёшь мне фотографию, '
                'я отправлю тебе карту с указанием, где эта фотография была сделана',
        'bye': 'Бот прощается с вами!'
            },

    'en-US': {
        'menu_header': 'Send photo or choose of one options below',
        'switch_lang_success': 'Now I\'m speaking English.',
        'switch_lang_failure': 'I can\'t change language. Try again later.',
        'dont_speak': ('I cannot speak, but if you send me a photo (as a file), I will send you back the location'
                       ' where it was taken, time of shooting and camera info.'),
        'as_file': ('Sorry, but it would be better if you send your photo as a file. If you send it just as a photo, '
                    'Telegram will get rid of location and data in order to compress the photo.'),
        'no_gps': 'This photo does not have info about location. Try another one.',
        'bad_gps': 'Cannot read GPS from this photo. Maybe @SavageRandy can help you.',
        'no_exif': 'This photo does not contain any data. Maybe you have another one?',
        'photo_prcs': 'Wait a sec... *sounds of heavy machinery*',
        'camera_info': ['Date: ', 'Camera brand: ', 'Lens brand: '],
        'top_cams': 'The most popular cameras/smartphones among user of the @photogpsbot',
        'top_lens': 'The most popular lens among user of the @photogpsbot',
        'oops': 'This feature is coming soon. But if you send me a photo (as a file), I will send you back the location'
                ' where it was taken',
        'bye': 'Goodbye! Bot is turning off...'
            }
}
