"""This file load secrets from .env file, pushes them to local system
environment and than get it back from there as variables"""

import os
from dotenv import load_dotenv
load_dotenv('.env')

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
DB_PASSWD = os.environ.get('DB_PASSWD')
SSH_USER = os.environ.get('SSH_USER')
SSH_PASSWD = os.environ.get('SSH_PASSWD')
MY_TELEGRAM = os.environ.get('MY_TELEGRAM')
PROXY_CONFIG = os.environ.get('PROXY_CONFIG')
SERVER_ADDRESS = os.environ.get('SERVER_ADDRESS')
DB_USER = os.environ.get('DB_USER')
DB_NAME = os.environ.get('DB_NAME')