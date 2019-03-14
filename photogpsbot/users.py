from photogpsbot import bot, log, log_files, db, user_language, messages


class User:
    def __init__(self, chat_id, first_name, last_name, nickname,
                 language='en-EN'):
        self.chat_id = chat_id
        self.first_name = first_name
        self.last_name = last_name
        self.nickname = nickname
        self._lang = language

    def set_language(self):
        pass

    def get_language(self):
        pass

    def switch_language(self):
        pass

    def __repr__(self):
        return (f'{self.first_name} {self.nickname} {self.last_name} '
                f'({self.chat_id}) preferred language: {self.get_language()}')


class Users:
    def __init__(self):
        self.users = {}

    def cache(self):
        # Caches most recent users from the database
        pass

    def clean_cache(self):
        # Remove the least active users from cache
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

    def find_by_chat_id(self, message):
        user = self.users.get(message.chat_id, None)
        if not user:
            user = self.add_new_one(messages)

        return user
