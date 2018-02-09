#!python3
# -*- coding: utf-8 -*-
# Tool to connect to xardbot database, which return MySQLdb.connect object

import MySQLdb
import os
import config

db = None
tunnel = None


def connect():

    global db
    global tunnel

    # if script is being opened from server where mysql database is running
    if os.path.exists('prod.txt'):
        try:
            db = MySQLdb.connect('OloloRodriguez.mysql.pythonanywhere-services.com', 'OloloRodriguez',
                                 config.db_password, 'OloloRodriguez$photogpsbot', charset='utf8')
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
        db = MySQLdb.connect(
            user='OloloRodriguez', password=config.db_password,
            host='127.0.0.1', port=tunnel.local_bind_port,
            database='OloloRodriguez$photogpsbot', charset='utf8'
        )
        return db


def disconnect():
    db.close()
    if tunnel is not None:
        tunnel.close()

    return True
