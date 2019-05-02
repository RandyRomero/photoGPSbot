"""
Module to manage users of bot: store and update information, interact with
the database, keep tack of and switch language of interface for a user
"""

import config
from photogpsbot import bot, log, db
from photogpsbot.db_connector import DatabaseError, DatabaseConnectionError

from telebot.types import Message
from typing import Tuple


class User:
    """
    Class that represents a user of photoGPSbot

    Class that represents one user of this Telegram bot and helps to store
    and retrieve basic info about him and his language of choice for
    interface of the bot
    """
    def __init__(self, chat_id, first_name, nickname, last_name,
                 language='en-US'):
        self.chat_id = chat_id
        self.first_name = first_name
        self.nickname = nickname
        self.last_name = last_name
        self.language = language

    def set_language(self, lang: str) -> None:
        """
        Update language of user in the User object and in the database

        :param lang: string with language tag like "en-US"
        :return: None
        """
        log.debug('Updating info about user %s language '
                  'in memory & database...', self)

        self.language = lang

        query = ("UPDATE users "
                 f"SET language=%s "
                 f"WHERE chat_id=%s")

        parameters = self.language, self.chat_id
        try:
            db.add(query, parameters)
        except DatabaseError:
            log.error("Can't add new language of %s to the database", self)
        else:
            log.debug('Language updated.')

    def switch_language(self) -> str:
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

    def __str__(self):
        return (f'{self.first_name} {self.nickname} {self.last_name} '
                f'({self.chat_id}) preferred language: {self.language}')

    def __repr__(self):
        return (f'{self.__class__.__name__}(chat_id={self.chat_id}, '
                f'first_name="{self.first_name}", nickname="{self.nickname}", '
                f'last_name="{self.last_name}", language="{self.language}")')


class Users:
    """
    Class for managing users of the bot

    The class let you find them, add to system,
    cache them from the database, check whether user changed his info etc
    """
    def __init__(self):
        self.users = {}

    @staticmethod
    def get_total_number() -> int:
        """
        Count the total number of users in the database

        :return: integer which is the total number of users
        """
        query = "SELECT COUNT(*) FROM users"
        try:
            cursor = db.execute_query(query)
        except DatabaseConnectionError:
            log.error("Can't count the total number of users!")
            raise

        return cursor.fetchone()[0]

    @staticmethod
    def get_last_active_users(limit: int) -> Tuple[Tuple[int, str, str, str,
                                                         str]]:
        """
        Get from the database a tuple of users who have been recently using
        the bot

        :param limit: integer that specifies how much users to get
        :return: tuple of tuples with user's info
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
                 f'DESC LIMIT %s')

        parameters = limit,

        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            log.error("Cannot get the last active users because of some "
                      "problems with the database")
            raise

        last_active_users = cursor.fetchall()
        log.debug(last_active_users)
        return last_active_users

    def cache(self, limit: int) -> None:
        """
        Caches last active users from database to a dictionary inside object of
        this class

        :param limit: limit of entries to be cached
        :return: None
        """

        log.debug("Start caching last active users from the DB...")

        try:
            last_active_users = self.get_last_active_users(limit)
        except DatabaseConnectionError:
            log.error("Cannot cache users!")
            return

        for items in last_active_users:
            # if chat_id of a user is not known to the program
            if items[0] not in self.users:
                # adding users from database to the "cache"
                self.users[items[0]] = User(*items)
                log.debug("Caching user: %s", self.users[items[0]])
        log.info('Users have been cached.')

    def clean_cache(self, limit: int) -> None:
        """
        Method that remove several User objects from cache - the least 
        active users

        :param limit: number of the users that the method should remove
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
                 f'LIMIT %s')

        parameters = limit,

        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:
            log.error("Can't figure out the least active users...")
            return

        if not cursor.rowcount:
            log.warning("There are no users in the db")
            return

        # Make list out of tuple of tuples that is returned by MySQL
        least_active_users = [chat_id[0] for chat_id in cursor.fetchall()]
        log.info('Removing %d least active users from cache...', limit)
        num_deleted_entries = 0
        for entry in least_active_users:
            log.debug('Deleting %s...', entry)
            deleted_entry = self.users.pop(entry, None)
            if deleted_entry:
                num_deleted_entries += 1
        log.debug("%d users were removed from cache.", num_deleted_entries)

    @staticmethod
    def _add_to_db(user: User) -> None:
        """
        Adds the User object to the database

        :param user: User object with info about user
        :return: None
        """
        query = ("INSERT INTO users (chat_id, first_name, nickname, "
                 "last_name, language) "
                 f"VALUES (%s, %s, %s, %s, %s)")

        parameters = (user.chat_id, user.first_name, user.nickname,
                      user.last_name, user.language)

        try:
            db.add(query, parameters)
        except DatabaseError:
            log.error("Cannot add user to the database")
        else:
            log.info(f"User {user} was successfully added to the users db")

    def add_new_one(self,
                    chat_id: int, first_name: str, nickname: str,
                    last_name: str, language: str,
                    add_to_db: bool = True) -> User:
        """
        Adds a new User in dictionary with users and to the database
        at one fell swoop

        :param chat_id: id of a Telegram user
        :param first_name: first name of a Telegram user
        :param nickname: nickname of a Telegram user
        :param last_name: last name of a Telegram user
        :param language: preferred language of a Telegram user
        :param add_to_db: whether of not to add user to the database (for
        example, if bot is caching users from the database, there is clearly
        no point to add them back to the database)
        :return: User object with info about the added user
        """
        user = User(chat_id, first_name, nickname, last_name, language)
        self.users[chat_id] = user
        if add_to_db:
            self._add_to_db(user)
        return user

    @staticmethod
    def compare_and_update(user, message: Message) -> None:
        """
        Updates user's info if needed

        This method compare a user object from the bot and his info from
        the Telegram message to check whether a user has changed his bio
        or not. If yes, the user object that represents him in the bot will
        be updated accordingly. Now this function is called only when a user
        asks the bot for showing the most popular cams

        :param user: user object that represents a Telegram user in this bot
        :param message: object from Telegram that contains info about user's
        message and about himself
        :return: None
        """

        log.info('Checking whether user have changed his info or not...')
        msg = message.from_user
        usr_from_message = User(message.chat.id, msg.first_name, msg.username,
                                msg.last_name)

        if user.chat_id != usr_from_message.chat_id:
            log.error("Wrong user to compare!")
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
        query = (f"UPDATE users "
                 f"SET first_name=%s, "
                 f"nickname=%s, "
                 f"last_name=%s "
                 f"WHERE chat_id=%s")

        parameters = (user.first_name, user.nickname, user.last_name,
                      user.chat_id)

        try:
            db.add(query, parameters)
        except DatabaseError:
            log.error("Could not update info about %s in the database",
                      user)
        else:
            log.debug("User's info has been updated")

    def find_one(self, message: Message) -> User:
        """
        Look up a user by a message which we get together with request
        from Telegram

        :param message: object from Telegram that contains info about user's
        message and about himself
        :return: user object that represents a Telegram user in this bot
        """

        # look up user in the cache of the bot
        user = self.users.get(message.chat.id, None)

        if user:
            return user

        # otherwise look up the user in the database
        log.debug("Looking up the user in the database as it doesn't "
                  "appear in cache")
        query = (f'SELECT first_name, nickname, last_name, language '
                 f'FROM users '
                 f'WHERE chat_id=%s')

        parameters = message.chat.id,
        try:
            cursor = db.execute_query(query, parameters)
        except DatabaseConnectionError:

            # Even if the database in unreachable add user to dictionary
            # with users otherwise the bot will crash requesting this
            # user's info
            log.error('Cannot lookup the user with chat_id %d in database',
                      message.chat.id)
            msg = message.from_user
            user = self.add_new_one(message.chat.id, msg.first_name,
                                    msg.last_name, msg.username,
                                    language='en-US', add_to_db=False)
            return user

        if not cursor.rowcount:
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

        # finally if the user wasn't found in the cache of the bot, but was
        # found in the database
        else:
            log.debug('User %d has been found in the database',
                      message.chat.id)

            user_data = cursor.fetchall()[0]
            user = self.add_new_one(message.chat.id, *user_data,
                                    add_to_db=False)

        return user

    def __str__(self):
        return ('Instance of a handler of users. '
                f'There is {len(self.users)} users in cache right now.')
