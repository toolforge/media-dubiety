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

from __future__ import unicode_literals

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

interrupt = threading.Event()


class MediaDubietyIRC(
    ib3.auth.SASL,
    ib3.connection.SSL,
    ib3.mixins.DisconnectOnError,
    ib3.mixins.PingServer,
    ib3.mixins.RejoinOnBan,
    ib3.mixins.RejoinOnKick,
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
            channels=ircconf['channels'],
        )
        threading.Thread.__init__(self, name='IRC')

        self.reactor.scheduler.execute_every(
            period=1, func=self.check_interrupt)

    def run(self):  # Override threading.Thread
        super(MediaDubietyIRC, self).start()
        # ib3.Bot.start(self)

    def start(self):  # Override ib3.Bot
        threading.Thread.start(self)

    def check_interrupt(self):
        if interrupt.isSet():
            raise KeyboardInterrupt


class MediaDubietySSE(threading.Thread):
    def __init__(self):
        super(MediaDubietySSE, self).__init__(name='SSE')

    def run(self):
        stream = EventStreams(stream='recentchange')
        for event in stream:
            if interrupt.isSet():
                raise KeyboardInterrupt
            # print(event)


def main():
    irc = MediaDubietyIRC(ircconf)
    sse = MediaDubietySSE()
    irc.start()
    sse.start()
    try:
        while irc.isAlive() or sse.isAlive():
            try:
                irc.join(0)
            except RuntimeError:
                pass
            try:
                sse.join(0)
            except RuntimeError:
                pass

            time.sleep(1)
    except KeyboardInterrupt:
        interrupt.set()
        raise


if __name__ == '__main__':
    main()
