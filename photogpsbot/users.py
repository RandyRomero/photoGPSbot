import config
from photogpsbot import bot, log, db, send_last_logs

# todo write description for classes and methods
# todo update user info like name and whatever if it was changed


class User:
    def __init__(self, chat_id, first_name, nickname, last_name,
                 language='en-US'):
        self.chat_id = chat_id
        self.first_name = first_name
        self.nickname = nickname
        self.last_name = last_name
        self.language = language

    def set_language(self, lang):
        """
        Sets opposite language tag of what user had before. Methods
        adds new language tag in a database and in dictionary
        :return: None
        """
        log.debug('Updating info about user %s language '
                  'in memory & database...', self)

        self.language = lang

        query = ('UPDATE users '
                 f'SET language="{self.language}" '
                 f'WHERE chat_id={self.chat_id}')

        if not db.add(query):
            log.error("Can't add new language of %d to the database", self)
            send_last_logs()

    def switch_language(self):
        # Switch language from Russian to English or conversely
        curr_lang = self.language
        new_lang = 'ru-RU' if self.language == 'en-US' else 'en-US'
        log.info('Changing user %s language from %s to %s...', self,
                 curr_lang, new_lang)

        self.set_language(new_lang)

        return new_lang

    def __repr__(self):
        return (f'{self.first_name} {self.nickname} {self.last_name} '
                f'({self.chat_id}) preferred language: {self.language}')


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
        # todo try to return info about last active users by one query
        #  instead of two

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
            send_last_logs()
            return
        if not cursor.rowcount:
            log.warning('There are no entries in the photo_queries_table2')
            send_last_logs()
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
            send_last_logs()
            return
        if not cursor.rowcount:
            log.warning('There are no users in the db')
            send_last_logs()
            return

        users = cursor.fetchall()
        for items in users:
            # if chat_id of a user is not known to the program
            if items[0] not in self.users:
                self.users[items[0]] = User(*items)
                # users.add_new_one(*items, add_to_db=False)
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
                 f'"{user.nickname}", "{user.last_name}", "{user.language}")')
        if not db.add(query):
            log.error("Cannot add user to the database")
            send_last_logs()
        else:
            log.info(f"User {user} was successfully added to the users db")

    def add_new_one(self, chat_id, first_name, nickname, last_name, language,
                    add_to_db=True):
        """
        Function to add a new User in dictionary with users and to the database
        at one fell swoop
        :param chat_id: id of a Telegram user
        :param first_name: first name of a Telegram user
        :param nickname: nickname of a Telegram user
        :param last_name: last name of a Telegram user
        :param language: preferred language of a Telegram user
        :param add_to_db: whether of not to add user to the database (for
        example, if bot is caching users from the database, there is clearly
        no point to add them back to the database
        :return: User object with info about added user
        """
        user = User(chat_id, first_name, nickname, last_name, language)
        self.users[chat_id] = user
        if add_to_db:
            self._add_to_db(user)
        return user

    # todo make separate function find_by_id

    def find_by_id(self, chat_id):
        # Look up user by chat_id - usually when the bot caches users from the
        # datatable of users' queries
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

    def find_one(self, message):

        # Look up a user by a Message object which we get together with request
        # from Telegram
        user = self.users.get(message.chat.id, None)

        if not user:
            log.debug("Looking up the user in the database as it doesn't "
                      "appear in cache")
            query = (f'SELECT first_name, nickname, last_name, language '
                     f'FROM users '
                     f'WHERE chat_id={message.chat.id}')

            cursor = db.execute_query(query)
            if not cursor:
                # Even if the database in unreachable add user to dictionary
                # with users otherwise the bot will crash requesting this
                # user's info
                log.error('Cannot lookup the user with chat_id %d in database',
                          message.chat.id)
                send_last_logs()
                msg = message.from_user
                user = self.add_new_one(message.chat.id, msg.first_name,
                                        msg.last_name, msg.username,
                                        language='en-US', add_to_db=False)

            elif not cursor.rowcount:
                # This user uses our photoGPSbot for the first time as we
                # can't find him in the database
                log.info('Adding totally new user to the system...')
                msg = message.from_user
                user = self.add_new_one(message.chat.id, msg.first_name,
                                        msg.last_name, msg.username,
                                        language='en-US')
                bot.send_message(config.MY_TELEGRAM,
                                 text=f'You have a new user! {user}')
                log.info('You have a new user! Welcome %s', user)

            else:
                log.debug('User %d has been found in the database',
                          message.chat.id)

                user_data = cursor.fetchall()[0]
                user = self.add_new_one(message.chat.id, *user_data,
                                        add_to_db=False)

        return user
