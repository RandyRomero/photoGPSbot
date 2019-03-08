"""
Module that provides a way to connect to MySQL and reconnect each time
connection is lost. It also can automatically set up SSH tunnel thanks to
sshtunnel module

Original way to do it was described at
https://help.pythonanywhere.com/pages/ManagingDatabaseConnections/
"""

import socket
import traceback

# goes as mysqlclient in requirements
import MySQLdb
import sshtunnel

from photogpsbot import log, send_last_logs
import config


class Database:
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
        photogpsbot is located
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

    def execute_query(self, query, trials=0):
        """
        Executes a given query
        :param query: query to execute
        :return: cursor object
        """
        if not self.conn or not self.conn.open:
            self._connect()

        try:
            cursor = self.conn.cursor()
            log.debug('Executing query...')
            cursor.execute(query)
            log.debug('The query executed successfully')
            return cursor

        # try to reconnect if MySQL server has gone away
        except MySQLdb.OperationalError as e:

            # (2013, Lost connection to MySQL server during query)
            # (2006, Server has gone away)
            if e.args[0] in [2006, 2013]:
                log.info(e)
                log.debug("Connecting to the MySQL again...")

                self._connect()
                if trials > 3:
                    send_last_logs()
                    return None

                trials += 1
                # trying to execute query one more time
                self.execute_query(query)
            else:
                log.error(e)
                send_last_logs()
        except Exception:
            error = traceback.format_exc()
            log.error(error)
            send_last_logs()

    def add(self, query):
        """
        Shortcut to add something to a database
        :param query: query to execute
        :return: boolean - True if the method succeeded and False otherwise
        """

        if self.execute_query(query):
            self.conn.commit()
            return True
        else:
            return False

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
