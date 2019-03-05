import logging
import collections


class TailLogHandler(logging.Handler):

    def __init__(self, log_queue):
        logging.Handler.__init__(self)
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.append(self.format(record))


class TailLogger(object):

    def __init__(self, maxlen):
        self._log_queue = collections.deque(maxlen=maxlen)
        self._log_handler = TailLogHandler(self._log_queue)

    def contents(self):
        results = []
        for each in self._log_queue:
            results.append(each)
        self._log_queue.clear()
        return(results)
        #return '\n'.join(self._log_queue)

    @property
    def log_handler(self):
        return self._log_handler

tail = TailLogger(500)