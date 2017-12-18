import random
import threading


class BoundedQueueList(object):
    def __init__(self, max_length):
        self.max_length = max_length
        self.list = []
        self.lock = threading.RLock()

    def append(self, item):
        with self.lock:
            if len(self.list) == self.max_length:
                self.popfirst()

            self.list.append(item)

    def popfirst(self):
        with self.lock:
            return self.list.pop(0)

    def remove(self, value):
        with self.lock:
            self.list.remove(value)

    def __contains__(self, value):
        with self.lock:
            return value in self.list


class RecheckingList():
    def __init__(self, gen, recheck=0.1):
        self.gen = gen
        self.list = self.gen()
        self.recheck = recheck
        self.lock = threading.RLock()

    def __contains__(self, value):
        locked = self.lock.acquire(False)
        if random.random < self.recheck and locked:
            try:
                self.list = self.gen()
                return value in self.list
            finally:
                self.lock.release()
        elif locked:
            try:
                return value in self.list
            finally:
                self.lock.release()
        else:
            with self.lock:
                return value in self.list
