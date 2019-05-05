"""
Module that provides a way to connect to the MySQL and reconnect each time
connection is lost. It also can automatically set up SSH tunnel thanks to
sshtunnel module

The original way to do it was described at
https://help.pythonanywhere.com/pages/ManagingDatabaseConnections/
"""

import socket
from typing import Optional

# goes as mysqlclient in requirements
import MySQLdb  # type: ignore
from MySQLdb.connections import Connection  # type: ignore
import sshtunnel  # type: ignore
from sshtunnel import SSHTunnelForwarder  # type: ignore

from photogpsbot import log
import config


class DatabaseError(Exception):
    pass


class DatabaseConnectionError(Exception):
    pass


class Database:
    """
    Class that connects the bot to a database

    It provides methods to execute queries and handles connection to
    a MySQL database directly and via ssh if necessary
    """
    conn: Optional[Connection] = None
    tunnel: Optional[SSHTunnelForwarder] = None
    tunnel_opened: bool = False

    def _open_ssh_tunnel(self) -> None:
        """
        Method that opens a new ssh tunnel to the server where the database of
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

    def connect(self) -> None:
        """
        Connects the bot to a database

        Established connection either to a local database or to a remote one if
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

    def execute_query(self, query: str, parameters: tuple = None,
                      trials: int = 0):
        """
        Executes a given query

        :param query: query to execute
        :param parameters: parameters for query
        :param trials: integer that denotes number of trials to execute
        a query in case of known errors
        :return: cursor object
        """
        if not self.conn or not self.conn.open:
            self.connect()

        try:
            cursor = self.conn.cursor()
            cursor.execute(query, parameters)

        # try to reconnect if MySQL server has gone away
        except MySQLdb.OperationalError as e:

            # (2013, Lost connection to MySQL server during query)
            # (2006, Server has gone away)
            if e.args[0] in [2006, 2013]:
                log.info(e)

                self.connect()
                if trials <= 3:
                    # trying to execute query one more time
                    trials += 1
                    log.warning(e)
                    log.info("Trying execute the query again...")
                    return self.execute_query(query, parameters, trials)

                if trials > 3:
                    log.error(e)
                    log.warning("Ran out of limit of trials...")
                    raise DatabaseConnectionError("Cannot connect to the "
                                                  "database")
            else:
                log.error(e)
                raise
        except Exception as e:
            log.error(e)
            raise
        else:
            return cursor

    def add(self, query: str, parameters: tuple = None):
        """
        Shortcut to add something to a database

        :param query: query to execute
        :param parameters: parameters for query
        :return: boolean - True if the method succeeded and False otherwise
        """

        try:
            self.execute_query(query, parameters)
            self.conn.commit()
        except Exception as e:
            log.error(e)
            raise DatabaseError("Cannot add your data to the database!")

    def disconnect(self) -> bool:
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

    def __str__(self) -> str:
        return (f'Instance of a connector to the database. '
                f'The connection is {"opened" if self.conn else "closed"}. '
                f'SSH tunnel is {"opened" if self.tunnel_opened else "closed"}'
                '.')
