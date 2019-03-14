import config
from photogpsbot import bot, log, db, send_last_logs

# todo write description for classes and methods


class User:
    def __init__(self, chat_id, first_name, last_name, nickname,
                 language='en-EN'):
        self.chat_id = chat_id
        self.first_name = first_name
        self.last_name = last_name
        self.nickname = nickname
        self._lang = language

    def set_language(self, lang):
        """
        Sets opposite language tag of what user had before. Methods
        adds new language tag in a database and in dictionary
        :return: None
        """
        log.debug('Updating info about user %d language '
                  'in memory & database...', self.chat_id)

        self._lang = lang

        query = ('UPDATE users '
                 f'SET language={self._lang} '
                 f'WHERE chat_id={self.chat_id}')

        if not db.add(query):
            log.error("Can't add new language of %d to the database", self)
            send_last_logs()

        return

    def get_language(self):
        if self._lang:
            return self._lang

        query = f'SELECT language WHERE chat_id={self.chat_id}'
        cursor = db.cursor(query)
        if not cursor:
            log.error("Can't get language of %s because of some database "
                      "bug. Check db_connector logs. Setting user'slanguage "
                      "to default - en-US", self)
            send_last_logs()
            # returning default language
            self._lang = 'en-US'
            return self._lang

        # There is no language tag for this user in the database
        # which means this user is here for the first time
        elif not cursor.rowcount:
            bot.send_message(config.MY_TELEGRAM,
                             text='You have a new user!')
            log.info('%s default language for bot is set to be en-US.', self)
            self._lang = 'en-US'
            query = ('INSERT INTO users (chat_id, language) '
                     f'VALUES ({self.chat_id}, {self._lang}')
            db.add(query)
            return self._lang

        lang = cursor.fetchone()[0]
        self._lang = lang
        return lang

    def switch_language(self):
        # Switch language from Russian to English or conversely
        curr_lang = self._lang
        new_lang = 'ru-RU' if self._lang == 'en-US' else 'en-US'
        log.info('Changing user %s language from %s to %s...', self,
                 curr_lang, new_lang)

        self.set_language(new_lang)

        return new_lang

    def __repr__(self):
        return (f'{self.first_name} {self.nickname} {self.last_name} '
                f'({self.chat_id}) preferred language: {self.get_language()}')


class Users:
    def __init__(self):
        self.users = {}

    def cache(self):
        # Caches most recent users from the database
        # todo implement caching function
        pass

    def clean_cache(self):
        # Remove the least active users from cache
        # todo implement cleaning cache
        pass

    @staticmethod
    def _add_to_db(user):
        query = (f'INSERT INTO users (chat_id, first_name, '
                 'nickname, last_name, language) '
                 f'VALUES ({user.chat_id}, {user.first_name}, '
                 f'{user.nickname}, {user.last_name}, {user._lang})')
        if not db.add(query):
            log.warning("Cannot add user into database")
        else:
            log.info(f"User {user} was successfully added to the users db")

    def add_new_one(self, message):
        chat_id = message.chat_id
        msg = message.from_user
        user = User(chat_id, msg.first_name, msg.last_name, msg.username)
        self.users[chat_id] = user
        self._add_to_db(user)
        return user

    def find_user(self, message):
        user = self.users.get(message.chat_id, None)
        if not user:
            user = self.add_new_one(message)

        return user
