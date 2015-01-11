#!/usr/bin/env python3
# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

"""
__init__.py

The pearbot database submodule.

Copyright (c) 2015 Twisted Pear <pear at twistedpear dot at>
See the file LICENSE for copying permission.
"""

__all__ = ["create_engine", "get_table"]

import asyncio
import aiopg.sa
import logging

from os import environ
from urllib.parse import urlparse

from .tables import METADATA


DATABASE_URL = environ["DATABASE_URL"]
DATABASE = urlparse(DATABASE_URL)
ENGINE = None
ENGINE_LOCK = asyncio.Lock()

logging.getLogger(__name__).addHandler(logging.NullHandler())


@asyncio.coroutine
def create_engine():
    """
    Create a new engine for the Postgres database specified by the DATABASE_URL
    environment variable.
    """
    logger = logging.getLogger(__name__)
    logger.info("Creating engine for database {database} on {host}.".format(
        database=DATABASE.path[1:], host=DATABASE.hostname))

    engine = yield from aiopg.sa.create_engine(host=DATABASE.hostname,
                                               port=DATABASE.port,
                                               database=DATABASE.path[1:],
                                               user=DATABASE.username,
                                               password=DATABASE.password,
                                               minsize=1, maxsize=5)
    return engine


@asyncio.coroutine
def get_engine():
    """
    Get the global database engine object.
    A new engine is created in case no global object exists yet.
    """
    with (yield from ENGINE_LOCK):
        global ENGINE
        if not ENGINE:
            ENGINE = yield from create_engine()
        return ENGINE


def get_table(table):
    """Get a table definition from the module's MetaData object."""
    tables = METADATA.tables
    if table not in tables:
        raise KeyError("No such table: {table}.".format(table=table))
    return tables[table]