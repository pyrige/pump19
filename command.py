#!/usr/bin/env python3
# vim:fileencoding=utf-8:ts=8:et:sw=4:sts=4:tw=79

"""
command.py

Handle commands received on IRC.

Copyright (c) 2018 Twisted Pear <tp at pump19 dot eu>
See the file LICENSE for copying permission.
"""

import aiomc
import asyncio
import functools
import locale
import logging
import re
import songs
import twitch

BINGO_URL = "https://pump19.eu/bingo"
COMMAND_URL = "https://pump19.eu/commands"
LRRMC_SERVERS = {
    "vanilla": {
        "name": "the LRR Vanilla Minecraft Server",
        "host": "minecraft.darkmorford.net",
        "port": 25565,
        "info": "Check http://minecraft.darkmorford.net:8123/ "
                "for the dynamic map."
    },
    "snorsh": {
        "name": "the LRR Modded Minecraft Server",
        "host": "ftb.darkmorford.net",
        "port": 25565,
        "info": "One up James on SnorshCraft."
    }
}

CMD_REGEX = {
    "vod":
        re.compile("^vod$"),
    "clip":
        re.compile("^clip$"),
    "lrrmc":
        re.compile("^(?:lrrmc|⛏️)(?: (?P<server>\w+))?$"),
    "lastfm":
        re.compile("^(?:last\.fm|🎵) (?P<user>\w+)$", re.ASCII),
    "roll":
        re.compile("^(?:roll|🎲)(?: (?P<count>\d+)?d(?P<sides>\d+))?"),
    "bingo":
        re.compile("^bingo$"),
    "help":
        re.compile("^help|🚑$")
}

# set up locale for currency formatting (patreon command wants that)
locale.setlocale(locale.LC_MONETARY, "en_US.utf8")


class CommandHandler:
    """
    The command handler interacts with an IRC client and dispatches commands.
    It registers itself as a handler for PRIVMSG events.
    """
    logger = logging.getLogger("command")

    class Limiter:
        """
        A decorator that suppresses method calls within a certain time span.
        """

        logger = logging.getLogger("command.limiter")

        def __init__(self, *, span=15, loop=None):
            """Initialize rate limiter with a default delay of 15."""
            self.span = span
            self.loop = loop or asyncio.get_event_loop()

        def __call__(self, func):

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                now = self.loop.time()
                if (now - wrapper._spam_last) > wrapper._spam_span:
                    wrapper._spam_last = now
                    await func(*args, **kwargs)
                else:
                    self.logger.warning("Suppressed call to {name}.".format(
                        name=func.__name__))

            # each wrapper remembers its own delay and last call
            wrapper._spam_span = self.span
            wrapper._spam_last = 0.0

            return wrapper

    rate_limited = Limiter()

    class CommandRouter:
        """A simple router matching strings against a set of regular
           expressions match to a callable."""

        routes = list()

        def add_route(self, regex, callback):
            self.routes.append((regex, callback))

        def get_route(self, string):
            for (regex, callback) in self.routes:
                match = regex.fullmatch(string)
                if not match:
                    continue

                # add matching groups to function
                return functools.partial(callback, **match.groupdict())

            return None

    router = CommandRouter()

    def __init__(self, client, *, loop=None, prefix="&", override=None):
        """Initialize the command handler and register for PRIVMSG events."""
        self.logger.info("Creating CommandHandler instance.")

        self.prefix = tuple(prefix)
        self.override = override
        self.client = client
        self.client.event_handler("PRIVMSG")(self.handle_privmsg)
        self.loop = loop or asyncio.get_event_loop()
        self.rate_limited.loop = loop

        self.setup_routing()

    def setup_routing(self):
        """Connect command handlers to regular expressions using the router."""
        for key, regex in CMD_REGEX.items():
            cmd_name = "handle_command_{0}".format(key)
            handle_command = getattr(self, cmd_name, None)
            if handle_command and callable(handle_command):
                self.router.add_route(regex, handle_command)

    async def handle_privmsg(self, nick, target, message, **kwargs):
        """
        Handle a PRIVMSG event and dispatch any command to the relevant method.
        """
        # ignore everything that's not a command with our prefix
        if not message.startswith(self.prefix) or len(message) < 2:
            return

        # remove prefix, regex will retrieve the arguments
        cmd = message[1:]

        self.logger.info("Got command \"{0}\" from {1}.".format(cmd, nick))

        # is this a query? if so, send messages to nick instead
        if target == self.client.nickname:
            target = nick

        # check if we can handle that command
        handle_command = self.router.get_route(cmd)
        if handle_command and callable(handle_command):
            await handle_command(target, nick)

    @rate_limited
    async def handle_command_vod(self, target, nick):
        """
        Handle !vod command.
        Post the most recent Twitch.tv broadcast.
        """
        broadcasts = await twitch.get_broadcasts(27132299, 1)
        vod = next(broadcasts, None)

        broadcast_msg = "Latest Broadcast: {0} [{2}] | {1}".format(*vod)

        await self.client.privmsg(target, broadcast_msg)

    @rate_limited
    async def handle_command_clip(self, target, nick):
        """
        Handle !clip command.
        Post the most viewed Twitch.tv clip.
        """
        clips = await twitch.get_top_clips("loadingreadyrun", 1)
        clip = next(clips, None)

        clip_msg = "Top Clip: {0} [{2}] | https://clips.twitch.tv/{1}".format(
                *clip)
        await self.client.privmsg(target, clip_msg)

    @rate_limited
    async def handle_command_lrrmc(self, target, nick, *, server="vanilla"):
        """
        Handle !lrrmc command.
        Query and post the status of the LRR Minecraft server.
        """
        server = LRRMC_SERVERS.get(server, LRRMC_SERVERS["vanilla"])
        # don't stall forever when querying status
        status_coro = aiomc.get_status(
            server["host"], server["port"],
            loop=self.loop)

        try:
            status = await asyncio.wait_for(status_coro, 2.0)
        except asyncio.TimeoutError:
            status = None

        base_msg = ("Join {name} on {host}:{port}! {info} "
                    "Current Status: {status}")

        if not status:
            no_lrrmc_msg = base_msg.format(**server, status="Unknown")
            await self.client.privmsg(target, no_lrrmc_msg)
            return

        try:
            nowp = status["players"]["online"]
            maxp = status["players"]["max"]
        except (KeyError, TypeError):
            nowp = maxp = "?"

        status_msg = "Online - {now}/{max} players".format(now=nowp, max=maxp)

        lrrmc_msg = base_msg.format(**server, status=status_msg)
        await self.client.privmsg(target, lrrmc_msg)

    @rate_limited
    async def handle_command_lastfm(self, target, nick, *, user=None):
        """
        Handle !last.fm command.
        Query information on the provided last.fm user handle and print the
        most recently listened track.
        """
        coro = songs.get_lastfm_info(user, loop=self.loop)

        info = await coro
        if not info:
            no_lastfm_msg = ("Cannot query last.fm user information for "
                             "{user}.".format(user=user))
            await self.client.privmsg(target, no_lastfm_msg)
            return

        name = info.get("name")
        live = info.get("live")
        track = info.get("track")
        artist = info.get("artist")

        if not track and not artist:
            no_lastfm_msg = ("Cannot query most recently played track for "
                             "{name}.".format(name=name))
            await self.client.privmsg(target, no_lastfm_msg)
            return

        tempus = "is listening" if live else "last listened"

        lastfm_msg = "{name} {tempus} to \"{track}\" by {artist}".format(
                name=name, tempus=tempus, track=track, artist=artist)
        await self.client.privmsg(target, lastfm_msg)

    @rate_limited
    async def handle_command_roll(self, target, nick, *,
                                  count=None, sides=None):
        await self.client.privmsg(
                target,
                "THIS is why we can't have nice things!")

    @rate_limited
    async def handle_command_bingo(self, target, nick):
        """
        Handle !bingo command.
        Posts a link to the Trope Bingo cards.
        """
        bingo_msg = ("Check out {url} "
                     "for our interactive Trope Bingo cards.").format(
                         url=BINGO_URL)
        await self.client.privmsg(target, bingo_msg)

    @rate_limited
    async def handle_command_help(self, target, nick):
        """
        Handle !help command.
        Posts a link to the golem's list of supported commands.
        """
        help_msg = ("Pump19 is run by Twisted Pear. "
                    "Check {url} for a list of supported commands.").format(
                        url=COMMAND_URL)
        await self.client.privmsg(target, help_msg)
