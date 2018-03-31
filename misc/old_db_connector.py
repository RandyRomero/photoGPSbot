#!python3
# -*- coding: utf-8 -*-
# Tool to connect to xardbot database, which return MySQLdb.connect object

import MySQLdb
import os
import config
from handle_logs import log

db = None
tunnel = None


def connect():

    global db
    global tunnel

    log.info('Connecting to database...')

    # if script is being opened from server where mysql database is running
    if os.path.exists('prod.txt'):
        try:
            db = MySQLdb.connect('OloloRodriguez.mysql.pythonanywhere-services.com', 'OloloRodriguez',
                                 config.db_password, 'OloloRodriguez$photogpsbot', charset='utf8')
            log.info('Connected to MySQL database.')
            return db
        except MySQLdb.OperationalError:
            return False

    else:
        # if file is running from some local machine
        import sshtunnel
        sshtunnel.SSH_TIMEOUT = 5.0
        sshtunnel.TUNNEL_TIMEOUT = 5.0
        tunnel = sshtunnel.SSHTunnelForwarder(
            'ssh.pythonanywhere.com',
            ssh_username='OloloRodriguez', ssh_password=config.python_anywhere_password,
            remote_bind_address=('OloloRodriguez.mysql.pythonanywhere-services.com', 3306))
        tunnel.start()
        log.info('SSH tunnel has been established.')
        db = MySQLdb.connect(
            user='OloloRodriguez', password=config.db_password,
            host='127.0.0.1', port=tunnel.local_bind_port,
            database='OloloRodriguez$photogpsbot', charset='utf8'
        )
        log.info('Connected to MySQL database.')
        return db


def disconnect():
    db.close()
    log.info('Connection to database is closed.')
    if tunnel is not None:
        tunnel.close()
        log.info('SSH tunnel to Pythonanywhere is closed.')

    return True
