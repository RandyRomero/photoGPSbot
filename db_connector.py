#!python3
# -*- coding: utf-8 -*-

# Module that provides a way to connect ot MySQL and reconnect each time connection is lost. It also can
# automatically set up SSH tunnel thank to sshtunnel module

# Original way to do it was described at https://help.pythonanywhere.com/pages/ManagingDatabaseConnections/

import MySQLdb
import os
import config
from handle_logs import log


class DB:
    conn = None
    tunnel = None
    tunnel_opened = False

    def open_ssh_tunnel(self):
        log.info('Establishing SSH tunnel to database...')
        import sshtunnel
        sshtunnel.SSH_TIMEOUT = 5.0
        sshtunnel.TUNNEL_TIMEOUT = 5.0
        self.tunnel = sshtunnel.SSHTunnelForwarder(
            'ssh.pythonanywhere.com',
            ssh_username='OloloRodriguez', ssh_password=config.python_anywhere_password,
            remote_bind_address=('OloloRodriguez.mysql.pythonanywhere-services.com', 3306))
        self.tunnel.start()
        self.tunnel_opened = True
        log.info('SSH tunnel has been established.')

    def connect(self):
        log.info('Connecting to database...')
        self.conn = MySQLdb.connect('OloloRodriguez.mysql.pythonanywhere-services.com', 'OloloRodriguez',
                                    config.db_password, 'OloloRodriguez$photogpsbot', charset='utf8')
        log.info('Success.')

    def connect_through_ssh(self):
        log.info('Connecting to database through SSH...')
        try:
            self.conn = MySQLdb.connect(
                user='OloloRodriguez', password=config.db_password,
                host='127.0.0.1', port=self.tunnel.local_bind_port,
                database='OloloRodriguez$photogpsbot', charset='utf8'
            )
            log.info('Success')
        except:
            log.error('Can\'t open SSH tunnel')

    def execute_query(self, query):
        try:
            cursor = self.conn.cursor()
            log.info('Executing query...')
            cursor.execute(query)
            log.info('Success')
        except(AttributeError, MySQLdb.OperationalError):
            if os.path.exists('prod.txt'):
                self.connect()
            else:
                if self.tunnel_opened:
                    self.connect_through_ssh()
                else:
                    self.open_ssh_tunnel()
                    self.connect_through_ssh()

            cursor = self.conn.cursor()
            log.info('Executing query...')
            cursor.execute(query)
            log.info('Success')
        return cursor

    def disconnect(self):
        self.conn.close()
        if self.tunnel:
            self.tunnel.stop()
        self.tunnel_opened = False
        return True
