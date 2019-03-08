import config
from photogpsbot import bot, log, db, send_last_logs


class UserLanguage:

    def __init__(self):
        # Dictionary that contains user_id -- preferred language
        # for every active user
        self.user_lang = {}

    def cache(self, max_users):
        """
        Method that caches preferred language of last active users from
        database to a variable
        :param max_users: number of entries to be cached
        :return: True if it completed work without errors, False otherwise
        """

        log.debug('Caching users\' languages from DB...')

        # Select id of last active users
        query = ("SELECT chat_id "
                 "FROM photo_queries_table "
                 "GROUP BY chat_id "
                 "ORDER BY MAX(time) "
                 "DESC LIMIT {};".format(max_users))

        log.info('Figure out last active users...')
        cursor = db.execute_query(query)
        if not cursor:
            log.error("Can't figure out last active users! Check logs")
            return
        if not cursor.rowcount:
            log.warning('There are no users in the db')
            return

        last_active_users_tuple_of_tuples = cursor.fetchall()
        # Make list out of tuple of tuples that is returned by MySQL
        last_active_users = [chat_id[0] for chat_id in
                             last_active_users_tuple_of_tuples]

        log.debug('Caching language preferences for %d '
                  'last active users from database...', max_users)
        # Select from db with language preferences of users who
        # were active recently
        query = ("SELECT chat_id, lang "
                 "FROM user_lang_table "
                 "WHERE chat_id in {};".format(tuple(last_active_users)))

        cursor = db.execute_query(query)
        if not cursor:
            log.error("Can't cache language preferences for last active "
                      "users from the db")
            return
        if not cursor.rowcount:
            log.warning('There are no users in the db')
            return

        languages_of_users = cursor.fetchall()
        for chat_id, user_lang in languages_of_users:
            log.debug('chat_id: %d, language: %s', chat_id, user_lang)
            self.user_lang[chat_id] = user_lang
        log.info('Users languages were cached.')

    def clean_cache(self, max_users):
        # Function to clean RAM from language preferences of users
        # who used a bot a long time ago

        # Select users that the least active recently
        user_ids = tuple(self.user_lang.keys())
        query = ('SELECT chat_id '
                 'FROM photo_queries_table '
                 'WHERE chat_id in {} '
                 'GROUP BY chat_id '
                 'ORDER BY MAX(time) '
                 'LIMIT {}'.format(user_ids, max_users))

        log.info('Figuring out the least active users...')
        cursor = db.execute_query(query)
        if not cursor:
            log.error("Can't figure out the least active users...")
            return
        if not cursor.rowcount:
            log.warning("There are no users in the db")
            return

        least_active_users_tuple_of_tuples = cursor.fetchall()
        # Make list out of tuple of tuples that is returned by MySQL
        least_active_users = [chat_id[0]
                              for chat_id
                              in least_active_users_tuple_of_tuples]
        log.info('Removing language preferences of %d least '
                 'active users from memory...', max_users)
        num_deleted_entries = 0
        for entry in least_active_users:
            log.debug('Deleting {}...'.format(entry))
            deleted_entry = self.user_lang.pop(entry, None)
            if deleted_entry:
                num_deleted_entries += 1
        log.debug("%d entries with users language preferences "
                  "were removed from RAM.", num_deleted_entries)
        return

    def set(self, chat_id, lang):
        # Function to set language for a user

        log.debug('Updating info about user {} '
                  'language in memory & database...'.format(chat_id))
        query = ('UPDATE user_lang_table '
                 'SET lang="{}" '
                 'WHERE chat_id={}'.format(lang, chat_id))
        if not db.add(query):
            log.error("Can't add new language of %d to the database", chat_id)
            send_last_logs()

        self.user_lang[chat_id] = lang

        # Actually we can set length to be much more,
        # but now I don't have a lot of users, but need to keep an eye whether
        # this function works well or not
        if len(self.user_lang) > 10:
            self.clean_cache(2)

        log.info('User %s language was switched to %s', chat_id, lang)

    def get(self, chat_id):
        """
        Function to look up user language in dictionary
        (which is like cache), then in database (if it is not in dict).
        If there is not language preference for that user, set en-US by default.

        :param chat_id: user_id
        :return: language tag like ru-RU, en-US as a string
        """
        # log.debug('Defining user %s language...', chat_id)
        lang = self.user_lang.get(chat_id, None)
        if not lang:
            query = ('SELECT lang '
                     'FROM user_lang_table '
                     'WHERE chat_id={}'.format(chat_id))

            cursor = db.execute_query(query)
            if not cursor:
                error_message = (
                    f"Can't get language of user with id {chat_id} because of "
                    "some database bug. Check db_connector logs. "
                    "Setting user'slanguage to default - en-US")

                log.error(error_message)
                send_last_logs()
                lang = 'en-US'
                self.user_lang[chat_id] = lang
                return lang

            # There is no language tag for this user in the database
            # which means this user is here for the first time
            elif not cursor.rowcount:
                lang = 'en-US'
                bot.send_message(config.MY_TELEGRAM,
                                 text='You have a new user!')
                log.info('User %s default language for bot is set '
                         'to be en-US.', chat_id)
                query = ('INSERT INTO user_lang_table (chat_id, lang) '
                         'VALUES ({}, "{}")'.format(chat_id, lang))
                db.execute_query(query)
                db.conn.commit()
                self.user_lang[chat_id] = lang
                return lang

            lang = cursor.fetchone()[0]
            self.user_lang[chat_id] = lang

            if len(self.user_lang) > 10:
                self.clean_cache(2)

        return lang

    def switch(self, chat_id, curr_lang):
        # Switch language from Russian to English or conversely
        new_lang = 'ru-RU' if curr_lang == 'en-US' else 'en-US'
        log.info('Changing user %s language from %s to %s...', chat_id,
                 curr_lang, new_lang)

        self.set(chat_id, new_lang)

        return new_lang
