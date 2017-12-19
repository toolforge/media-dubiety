from __future__ import unicode_literals

import Queue
import threading
import traceback

import ib3
import ib3.auth
import ib3.connection
import ib3.mixins
import ib3.nick

from pywikibot.comms.eventstreams import EventStreams


class IRCClient(
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
    def __init__(self, ircconf, channels):
        super(IRCClient, self).__init__(
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
        super(IRCClient, self).start()
        # ib3.Bot.start(self)

    def start(self):  # Override ib3.Bot
        threading.Thread.start(self)

    def check_interrupt(self):
        if self.interrupt_event.isSet():
            self.connection.disconnect('406 Not Acceptable')
            raise KeyboardInterrupt

    def stop(self):
        self.interrupt_event.set()

    def msg(self, channels, msg):
        if not self.has_primary_nick():
            return

        for i in range(0, len(msg), 500):
            self.connection.privmsg_many(channels, msg[i:i+500])


class SSEClient(threading.Thread):
    def __init__(self, handler):
        super(SSEClient, self).__init__(name='SSE')
        self.interrupt_event = threading.Event()
        self.handler = handler

    def run(self):
        stream = EventStreams(stream='recentchange')
        for event in stream:
            if self.interrupt_event.isSet():
                raise KeyboardInterrupt

            self.handler(event)

    def stop(self):
        self.interrupt_event.set()


class ThreadPoolThread(threading.Thread):
    def __init__(self, name, queue):
        super(ThreadPoolThread, self).__init__(name=name)
        self.interrupt_event = threading.Event()
        self.queue = queue

    def run(self):
        while True:
            try:
                f = self.queue.get(True, 1)
            except Queue.Empty:
                pass
            else:
                try:
                    f()
                except Exception:
                    traceback.print_exc()
                finally:
                    self.queue.task_done()

            if self.interrupt_event.isSet():
                raise KeyboardInterrupt

    def stop(self):
        self.interrupt_event.set()


class ThreadPool(object):
    def __init__(self, size, name='Pool'):
        self.lock = threading.RLock()
        self.name = name
        self.running = False
        self.threads = []
        self.size = 0
        self.queue = Queue.Queue()

        self.incr(size)

    def incr(self, n):
        with self.lock:
            for i in range(n):
                self.size += 1
                thread = ThreadPoolThread(
                    '%s-%d' % (self.name, self.size),
                    self.queue
                )
                self.threads.append(thread)
                if self.running:
                    thread.start()

    def decr(self, n):
        with self.lock:
            for i in range(n):
                self.size -= 1
                thread = self.threads.pop()
                if self.running:
                    thread.stop()

    def start(self):
        with self.lock:
            self.running = True
            for thread in self.threads:
                thread.start()

    def join(self):
        return self.queue.join()

    def stop(self):
        with self.lock:
            self.decr(self.size)
            self.running = False

    def process(self, f):
        self.queue.put(f)

    def isAlive(self):
        return bool(self.size) and self.running
