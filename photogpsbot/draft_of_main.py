from photogpsbot import bot, log, log_files, db, user_language, messages, users


class User:
    def __init__(self, chat_id, name, surname, nickname, ):
        self.chat_id = chat_id
        self.name = name
        self.surname = surname
        self.nickname = nickname
        self.language = user_language.get(chat_id)


@bot.message_handler(content_types=['document'])  # receive file
def handle_message_with_image(message):

    user = users.find_user(message)
    current_user_lang = user_language.get(chat_id)
    bot.reply_to(message, messages[current_user_lang]['photo_prcs'])
    msg = message.from_user
    log.info('Name: %s Last name: %s Nickname: %s ID: %d sent photo as a '
             'file.', msg.first_name, msg.last_name, msg.username, msg.id)

    file_id = bot.get_file(message.document.file_id)
    # Get temporary link to a photo that user has sent to bot
    file_path = file_id.file_path
    # Download photo that got telegram bot from user
    # todo fix this (we don't use prod anymore)
    if os.path.exists('prod.txt'):
        r = requests.get('https://api.telegram.org/file/bot{0}/{1}'
                         .format(config.TELEGRAM_TOKEN, file_path))
    else:
        r = requests.get('https://api.telegram.org/file/bot{0}/{1}'
                         .format(config.TELEGRAM_TOKEN, file_path),
                         proxies={'https': config.PROXY_CONFIG})

    # Get file-like object of user's photo
    user_file = BytesIO(r.content)

    image_handler = ImageHandler(user_file)

    image = image_handler.get_image()

    if image.country:
        save_user_query_info(camera_info, message, country)
    else:
        save_user_query_info(camera_info, message)

    others_with_this_cam = get_number_users_by_feature(camera,
                                                       'camera_name', chat_id)

    others_with_this_lens = (
        get_number_users_by_feature(lens, 'lens_name', chat_id)
        if lens else None)

    others_from_this_country = (
        get_number_users_by_feature(country[0], 'country_en', chat_id)
        if country else None)

    # Make user message about camera from exif
    info_about_shot = ''
    for tag, item in zip(messages[user_language.get(chat_id)]['camera_info'],
                         [date_time_str, camera, lens, address]):
        if item:
            info_about_shot += '*{}*: {}\n'.format(tag, item)

    info_about_shot += others_with_this_cam if others_with_this_cam else ''
    info_about_shot += ('\n' + others_with_this_lens
                        if others_with_this_lens else '')
    info_about_shot += ('\n' + others_from_this_country
                        if others_from_this_country else '')
