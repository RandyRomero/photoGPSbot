from photogpsbot import bot, log, log_files, db, user_language, messages


class User:
    def __init__(self, chat_id, first_name, last_name, nickname):
        self.chat_id = chat_id
        self.first_name = first_name
        self.last_name = last_name
        self.nickname = nickname
        self.language = user_language

    def switch_language(self):
        return self.language.switch(self.chat_id)

    def get_language(self):
        return self.language.get(self.chat_id)

    def __repr__(self):
        return (f'{self.first_name} {self.nickname} {self.last_name} '
                f'({self.chat_id})')


class Users:
    def __init__(self):
        self.users = []

    def add_new_one(self):
        pass

    def find_by_chat_id(self, message):
        for user in self.users:
            if user.chat_id == message.chat_id:
                return user
        else:
            chat_id = message.chat_id
            msg = message.from_user
            user = User(chat_id, msg.first_name, msg.last_name, msg.username)
            self.users.append(user)
            return user
