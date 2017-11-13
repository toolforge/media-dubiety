#! /usr/bin/env python
# -*- coding: UTF-8 -*-
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General License for more details.
#
# You should have received a copy of the GNU General License
# along with self program.  If not, see <http://www.gnu.org/licenses/>
#

from __future__ import print_function, unicode_literals

import collections
import fnmatch
import json
import threading
import time
import os

import ib3
import ib3.auth
import ib3.connection
import ib3.mixins
import ib3.nick

import pywikibot
from pywikibot.comms.eventstreams import EventStreams

with open(os.path.expanduser('~/.ircconf.json'), 'r') as f:
    ircconf = json.load(f)
with open(os.path.expanduser('~/channels.json'), 'r') as f:
    channels = json.load(f, object_pairs_hook=collections.OrderedDict)


class MediaDubietyIRC(
    ib3.auth.SASL,
    ib3.connection.SSL,
    ib3.mixins.DisconnectOnError,
    ib3.mixins.PingServer,
    # ib3.mixins.RejoinOnBan,
    # ib3.mixins.RejoinOnKick,
    ib3.nick.Regain,
    ib3.Bot,
    threading.Thread,
):
    def __init__(self, ircconf):
        super(MediaDubietyIRC, self).__init__(
            server_list=[
                (ircconf['server'], ircconf['port'])
            ],
            nickname=ircconf['nick'],
            realname=ircconf['realname'],
            ident_password=ircconf['password'],
            channels=channels.values(),
        )
        threading.Thread.__init__(self, name='IRC')

        self.interrupt_event = threading.Event()
        self.reactor.scheduler.execute_every(
            period=1, func=self.check_interrupt)

    def run(self):  # Override threading.Thread
        super(MediaDubietyIRC, self).start()
        # ib3.Bot.start(self)

    def start(self):  # Override ib3.Bot
        threading.Thread.start(self)

    def check_interrupt(self):
        if self.interrupt_event.isSet():
            self.connection.disconnect()
            raise KeyboardInterrupt

    def interrupt(self):
        self.interrupt_event.set()

    def msg(self, channels, msg):
        if not self.has_primary_nick():
            return

        self.connection.privmsg_many(channels, msg)


class MediaDubietySSE(threading.Thread):
    def __init__(self, irc):
        super(MediaDubietySSE, self).__init__(name='SSE')
        self.irc = irc
        self.interrupt_event = threading.Event()

    def run(self):
        stream = EventStreams(stream='recentchange')
        for event in stream:
            if self.interrupt_event.isSet():
                raise KeyboardInterrupt

            if (event['type'] == 'log' and
                    event['log_type'] in ['upload', 'block']):
                EventHandler(event, self.irc).start()

    def interrupt(self):
        self.interrupt_event.set()


class EventHandler(threading.Thread):
    def __init__(self, event, irc):
        super(EventHandler, self).__init__(
            name='Event %(wiki)s.%(id)d' % event)
        self.daemon = True
        self.event = event
        self.irc = irc

    def run(self):
        privmsg_channels = []
        for glob, channel in channels.items():
            if fnmatch.fnmatch(self.event['server_name'], glob):
                privmsg_channels.append(channel)
        self.irc.msg(privmsg_channels, self.event['meta']['uri'])


def main():
    irc = MediaDubietyIRC(ircconf)
    sse = MediaDubietySSE(irc)
    irc.start()
    sse.start()
    try:
        while irc.isAlive() and sse.isAlive():
            time.sleep(1)
    finally:
        sse.interrupt()
        irc.interrupt()
        for thread in threading.enumerate():
            if thread.daemon:
                print('Abandoning daemon thread %s' % thread.name)


if __name__ == '__main__':
    main()
