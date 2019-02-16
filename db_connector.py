"""
Module that provides a way to connect to MySQL and reconnect each time
connection is lost. It also can automatically set up SSH tunnel thanks to
sshtunnel module

Original way to do it was described at
https://help.pythonanywhere.com/pages/ManagingDatabaseConnections/
"""

import os

# goes as mysqlclient in requirements
import MySQLdb
import sshtunnel
import socket

import config
from handle_logs import log


class DB:
    """
    Class that provides method to execute queries and handles connection to
    the MySQL database directly and via ssh if necessary
    """
    conn = None
    tunnel = None
    tunnel_opened = False

    def _open_ssh_tunnel(self):
        """
        Method that opens ssh tunnel to the server where the database of
        photoGPSbot is located
        :return: None
        """
        log.debug('Establishing SSH tunnel to the server where the database '
                  'is located...')
        sshtunnel.SSH_TIMEOUT = 5.0
        sshtunnel.TUNNEL_TIMEOUT = 5.0
        self.tunnel = sshtunnel.SSHTunnelForwarder(
            ssh_address_or_host=config.SERVER_ADDRESS,
            ssh_username=config.SSH_USER,
            ssh_password=config.SSH_PASSWD,
            ssh_port=22,
            remote_bind_address=('127.0.0.1', 3306))

        self.tunnel.start()
        self.tunnel_opened = True
        log.debug('SSH tunnel has been established.')

    def _connect(self):
        """
        Established connection either to local database or to remote one if
        the script runs not on the same server where database is located
        :return: None
        """
        if socket.gethostname() == config.PROD_HOST_NAME:
            log.info('Connecting to the local database...')
            port = 3306
        else:
            log.info('Connecting to the database via SSH...')
            if not self.tunnel_opened:
                self._open_ssh_tunnel()

            port = self.tunnel.local_bind_port

        self.conn = MySQLdb.connect(host='127.0.0.1',
                                    user=config.DB_USER,
                                    password=config.DB_PASSWD,
                                    port=port,
                                    database=config.DB_NAME,
                                    charset='utf8')
        log.info('Connected to the database.')

    def execute_query(self, query):
        """
        Executes a given query
        :param query: query to execute
        :return: cursor object
        """
        if not self.conn or not self.conn.open:
            self._connect()

        try:
            cursor = self.conn.cursor()
        # try to reconnect if MySQL server has gone away
        except MySQLdb.OperationalError as e:
            if e[0] == 2006:
                log.info(e)
                log.info("Connecting to the MySQL again...")
                self._connect()
                self.execute_query(query)

        log.debug('Executing query...')
        cursor.execute(query)
        log.debug('The query executed successfully')
        return cursor

    def disconnect(self):
        """
        Closes the connection to the database and ssh tunnel if needed
        :return: True if succeeded
        """
        if self.conn:
            self.conn.close()
            log.info('Connection to the database has been closed.')
        if self.tunnel:
            self.tunnel.stop()
            log.info('SSH tunnel has been closed.')
        self.tunnel_opened = False
        return True
