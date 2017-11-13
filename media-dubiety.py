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
import datetime
import fnmatch
import json
import re
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

SITE = pywikibot.Site()

# Regexes source from Dispenser
stalkwords_R = re.compile(
    r'(Wikipedia|WP)[-. _\-]*(0|Zero)|T129845|Z591|Z567|Dispenser|HaeB|'
    r'Keegan|Koerner|Vito|Zhuyifei', re.I)
pirate_names_R = re.compile(
    r'(([Nn]+[Ee]+[Ww]+[Ss]+|[Nn]+[Ww]+[Ee]+[Ss]+|[Pp]ortal|[Mm]u[sz]ik|'
    r'[Mm]adezyma|Walter|Mr[.]?_Gamer|MRGAMER|Germano|[Aa]rlindo|[Aa]mbrosio|'
    r'[Hh]indio|[Ee]dman|Edgar|[Yy]ounes)[_.\-]?(?![^ ]*/))+')


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

    @staticmethod
    def check_wp0_usercat(username):
        testcat = 'Category:Users suspected of abusing Wikipedia Zero'
        commonsuser = pywikibot.User(SITE, username)
        for category in commonsuser.categories():
            if category.title() == testcat:
                return True
            for supercategory in category.categories():
                if supercategory.title() == testcat:
                    return True

        for userlist in [
            'User:Teles/Angola Facebook Case',
            'User:NahidSultan/Bangladesh Facebook Case/Accounts'
        ]:
            for linkeduser in pywikibot.Page(SITE, userlist).linkedPages():
                if linkeduser.title() == commonsuser.title():
                    return True

        return False

    @staticmethod
    def sizeof_fmt(num, suffix='B'):
        # Source: http://stackoverflow.com/a/1094933
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    def run(self):
        site = SITE.fromDBName(self.event['wiki'])
        user = pywikibot.User(site, self.event['user'])

        line = None

        if self.event['log_type'] == 'upload':
            filepage = pywikibot.FilePage(site, self.event['title'])
            revision = filepage.latest_file_info

            def file_is_evil():
                if EventHandler.check_wp0_usercat(user.username):
                    return True

                if revision.mime.startswith('image/'):
                    # try:
                    #     dim = revision.width * revision.height
                    # except (TypeError, AttributeError):
                    #     return True
                    #
                    # if revision.mime == 'image/jpeg':
                    #     if revision.size < 3 * dim + 10 << 20:
                    #         return False
                    # if revision.mime == 'image/png':
                    #     if revision.size < TODO:
                    #         return False
                    # else:
                        return False
                elif revision.mime == 'application/pdf':
                    numpages = int({
                        val['name']: val['value']
                        for val in revision.metadata
                    }.get('Pages', '0'))
                    if revision.size < (min(8, numpages) << 20):
                        return False

                user.getprops(True)
                if (user.editCount() > 20 or
                        user.registration() < datetime.datetime(2017, 1, 1)):
                    return False

                return True

            if not file_is_evil():
                return

            hasdelete = bool(list(
                site.logevents(logtype='delete', page=filepage, total=1)))
            groups = set(user.groups()) - set(['*', 'user', 'autoconfirmed'])

            line = '%s (%d %s%s) %s %s (%s)' % (
                ('http://tinyurl.com/CentralAuth/' + user.title(
                    underscore=True, asUrl=True, withNamespace=False)),
                user.editCount(),
                'edit' if user.editCount() == 1 else 'edits',
                (', \x0301,09%s\x0F' % ', '.join(groups)) if groups else '',
                ('re-uploaded' if hasdelete else 'uploaded'),
                self.event['meta']['uri'],
                ', '.join([x for x in (
                    self.sizeof_fmt(revision.size),
                    ('%d min' % (revision.duration / 60.0)
                        if hasattr(revision, 'duration') else ''),
                ) if x])
            )
            line = pirate_names_R.sub('\x0304\\g<0>\x0F', line)
        elif self.event['log_type'] == 'block':
            pass

        if line:
            privmsg_channels = []
            for glob, channel in channels.items():
                if fnmatch.fnmatch(self.event['server_name'], glob):
                    privmsg_channels.append(channel)
            self.irc.msg(privmsg_channels, line)


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
