#!/usr/bin/env python3
# vim:fenc=utf-8:ts=8:et:sw=4:sts=4:tw=79:ft=python

"""
config.py

The Pump19 IRC Golem configuration loader.
It reads configuratiom from environment variables and provides access to
component specific dictionaries.

Copyright (c) 2015 Twisted Pear <tp at pump19 dot eu>
See the file LICENSE for copying permission.
"""

from os import environ


def __get_irc_config():
    """Get a configuration dictionary for IRC specific settings."""
    channel_list = environ["PUMP19_IRC_CHANNELS"]
    channels = channel_list.split(";")

    return {"hostname": environ["PUMP19_IRC_HOSTNAME"],
            "port": int(environ["PUMP19_IRC_PORT"]),
            "ssl": True if "PUMP19_IRC_SSL" in environ else False,
            "password": environ.get("PUMP19_IRC_PASSWORD"),
            "nickname": environ["PUMP19_IRC_NICKNAME"],
            "username": environ["PUMP19_IRC_USERNAME"],
            "realname": environ["PUMP19_IRC_REALNAME"],
            "channels": channels}


def __get_cmd_config():
    """Get a configuration dictionary for a CommandHandler instance."""

    return {"prefix": environ.get("PUMP19_CMD_PREFIX", "!"),
            "override": environ.get("PUMP19_CMD_OVERRIDE")}


def get_config(component):
    """
    Get a configuration dictionary for a specific component.
    Valid components are:
    - irc
    """
    if component == "irc":
        return __get_irc_config()
    elif component == "cmd":
        return __get_cmd_config()

    # we don't know that config
    raise KeyError("No such component: {0}".format(component))
