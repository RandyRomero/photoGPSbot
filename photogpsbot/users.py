import config
from photogpsbot import bot, log, db, send_last_logs

# todo write description for classes and methods
# todo update user info like name and whatever if it was changed


class User:
    def __init__(self, chat_id, first_name, last_name, nickname,
                 language='en-US'):
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
        log.debug('Updating info about user %s language '
                  'in memory & database...', self)

        self._lang = lang

        query = ('UPDATE users '
                 f'SET language="{self._lang}" '
                 f'WHERE chat_id={self.chat_id}')

        if not db.add(query):
            log.error("Can't add new language of %d to the database", self)
            send_last_logs()

    def get_language(self):
        if self._lang:
            return self._lang

        query = f'SELECT language FROM users WHERE chat_id={self.chat_id}'
        cursor = db.execute_query(query)
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

        lang = cursor.fetchone()
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

    def cache(self, num_users):
        """
        Method that caches preferred language of last active users from
        database to a variable
        :param num_users: number of entries to be cached
        :return: True if it completed work without errors, False otherwise
        """

        log.debug("Start caching last active users from the DB...")

        # Select id of last active users
        query = ("SELECT chat_id "
                 "FROM photo_queries_table2 "
                 "GROUP BY chat_id "
                 "ORDER BY MAX(time) "
                 f"DESC LIMIT {num_users};")

        log.info('Figure out last active users...')
        cursor = db.execute_query(query)
        if not cursor:
            log.error("Can't figure out last active users! Check logs")
            return
        if not cursor.rowcount:
            log.warning('There are no entries in the photo_queries_table2')
            return

        # Make list out of tuple of tuples that is returned by MySQL
        last_active_users = [chat_id[0] for chat_id in cursor.fetchall()]

        log.debug('Getting language preferences for %d '
                  'last active users from database...', num_users)
        # Select from db with language preferences of users who
        # were active recently
        query = ("SELECT chat_id, first_name, nickname, last_name, "
                 "language "
                 "FROM users "
                 f"WHERE chat_id in {tuple(last_active_users)};")

        cursor = db.execute_query(query)
        if not cursor:
            log.error("Can't get language preferences for last active "
                      "users from the db")
            return
        if not cursor.rowcount:
            log.warning('There are no users in the db')
            return

        users = cursor.fetchall()
        for items in users:
            # if chat_id of a user is not known to the program
            if items[0] not in self.users:
                self.users[items[0]] = User(*items)
                log.debug("Caching user: %s", self.users[items[0]])
        log.info('Users have been cached.')

    def clean_cache(self, num_users):
        """
        Method that remove languages tags from cache for the least active users
        :param num_users: number of the users that the method should remove
        from cache
        :return: None
        """

        log.info('Figuring out the least active users...')
        # Select users that the least active recently
        user_ids = tuple(self.users.keys())
        query = ('SELECT chat_id '
                 'FROM photo_queries_table2 '
                 f'WHERE chat_id in {user_ids} '
                 'GROUP BY chat_id '
                 'ORDER BY MAX(time) '
                 f'LIMIT {num_users}')

        cursor = db.execute_query(query)
        if not cursor:
            log.error("Can't figure out the least active users...")
            return
        if not cursor.rowcount:
            log.warning("There are no users in the db")
            return

        # Make list out of tuple of tuples that is returned by MySQL
        least_active_users = [chat_id[0] for chat_id in cursor.fetchall()]
        log.info('Removing language preferences of %d least '
                 'active users from memory...', num_users)
        num_deleted_entries = 0
        for entry in least_active_users:
            log.debug('Deleting %s...', entry)
            deleted_entry = self.users.pop(entry, None)
            if deleted_entry:
                num_deleted_entries += 1
        log.debug("%d entries with users language preferences "
                  "were removed from RAM.", num_deleted_entries)

    @staticmethod
    def _add_to_db(user):
        query = ('INSERT INTO users (chat_id, first_name, nickname, '
                 'last_name, language) '
                 f'VALUES ({user.chat_id}, "{user.first_name}", '
                 f'"{user.nickname}", "{user.last_name}", "{user._lang}")')
        if not db.add(query):
            log.warning("Cannot add user into database")
        else:
            log.info(f"User {user} was successfully added to the users db")

    def add_new_one(self, message):
        chat_id = message.chat.id
        msg = message.from_user
        user = User(chat_id, msg.first_name, msg.last_name, msg.username)
        self.users[chat_id] = user
        self._add_to_db(user)
        return user

    def find_user(self, message=None, chat_id=None):

        # Look up user by chat_id - usually when the bot caches users from the
        # datatable of users' queries
        if chat_id:
            user = self.users.get(chat_id, None)
            if not user:
                query = 'SELECT * FROM users'
                cursor = db.execute_query(query)
                if not cursor:
                    log.error(f'Cannot look up the user with chat id {chat_id}'
                              ' in the database because of some db error')
                    return None
                if not cursor.rowcount:
                    log.error('There is definitely should be the user with '
                              f'chat id {chat_id} in the database, but some'
                              'how his is not there')
                    return None

            return user

        # Look up a user by a Message object which we get together with request
        # from Telegram
        user = self.users.get(message.chat.id, None)
        if not user:
            user = self.add_new_one(message)

        return user
