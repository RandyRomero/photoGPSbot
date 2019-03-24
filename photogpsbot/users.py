"""
Module to manage users of bot: store and update information, interact with
the database, keep tack of and switch language of interface for user
"""

import config
from photogpsbot import bot, log, db, send_last_logs

# todo write description for classes and methods
# todo move function from main which evaluates a total number of users


class User:
    """
    Class that describes one user of this Telegram bot and helps to store basic
    info about him and his language of choice for interface of the bot
    """
    def __init__(self, chat_id, first_name, nickname, last_name,
                 language='en-US'):
        self.chat_id = chat_id
        self.first_name = first_name
        self.nickname = nickname
        self.last_name = last_name
        self.language = language

    def set_language(self, lang):
        """
        Update language of user in the User object and in the database
        :param lang: string with language tag like "en-US"
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
        """
        Switch language from Russian to English or conversely
        :return: string with language tag like "en-US" to be used for
        rendering menus and messages for user
        """
        curr_lang = self.language
        new_lang = 'ru-RU' if self.language == 'en-US' else 'en-US'
        log.info('Changing user %s language from %s to %s...', self,
                 curr_lang, new_lang)

        self.set_language(new_lang)

        return new_lang

    def __repr__(self):
        """
        Override the default repr in order to give sensible information about
        a particular user
        :return: string with info about a user
        """
        return (f'{self.first_name} {self.nickname} {self.last_name} '
                f'({self.chat_id}) preferred language: {self.language}')


class Users:
    """
    Class for managing users of the bot: find them, add to system,
    cache them from the database, check whether user changed his info etc
    """
    def __init__(self):
        self.users = {}

    @staticmethod
    def get_last_active_users(limit):
        """
        Get from the database a tuple of users who have been recently using
        the bot
        :param limit: integer that specifies how much users to get
        :return: tuple of tuples with users info
        """
        log.info('Evaluating last active users with date of '
                 'last time when they used bot...')

        # From photo_queries_table2 we take chat_id of the last
        # active users and from 'users' table we take info about these
        # users by chat_id which is a foreign key
        query = ('SELECT p.chat_id, u.first_name, u.nickname, u.last_name, '
                 'u.language '
                 'FROM photo_queries_table2 p '
                 'INNER JOIN users u '
                 'ON p.chat_id = u.chat_id '
                 'GROUP BY u.chat_id, u.first_name, u.nickname, u.last_name, '
                 'u.language '
                 'ORDER BY MAX(time)'
                 f'DESC LIMIT {limit}')

        cursor = db.execute_query(query)
        if not cursor:
            log.error("Cannot get the last active users because of some "
                      "problems with the database")
            send_last_logs()
            return None

        last_active_users = cursor.fetchall()
        return last_active_users

    def cache(self, limit):
        """
        Caches last active users from database to a dictionary inside object of
        this class
        :param limit: limit of entries to be cached
        :return: None
        """

        log.debug("Start caching last active users from the DB...")

        last_active_users = self.get_last_active_users(limit)

        if not last_active_users:
            log.error("Cannot cache users")
            return

        for items in last_active_users:
            # if chat_id of a user is not known to the program
            if items[0] not in self.users:
                # adding users from database to the "cache"
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

    @staticmethod
    def compare_and_update(user, message):
        log.info('Checking whether user have changed his info or not...')
        msg = message.from_user
        usr_from_message = User(message.chat.id, msg.first_name, msg.username,
                                msg.last_name)

        if user.chat_id != usr_from_message.chat_id:
            log.error("Wrong user to compare!")
            send_last_logs()
            return

        if user.first_name != usr_from_message.first_name:
            user.first_name = usr_from_message.first_name

        elif user.nickname != usr_from_message.nickname:
            user.nickname = usr_from_message.nickname

        elif user.last_name != usr_from_message.last_name:
            user.last_name = usr_from_message.last_name

        else:
            log.debug("User's info hasn't changed")
            return

        log.info("User has changed his info")
        log.debug("Updating user's info in the database...")
        query = (f'UPDATE users '
                 f'SET first_name="{user.first_name}", '
                 f'nickname="{user.nickname}", '
                 f'last_name="{user.last_name}" '
                 f'WHERE chat_id={user.chat_id}')

        if not db.add(query):
            log.error("Could not update info about %s in the database",
                      user)
            return

        log.debug("User info has been updated")

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
