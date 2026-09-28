"""Loaded automatically by Python when this directory is on PYTHONPATH, which
preprocessing.py's align.sh sets for the `mfa` process only.

MFA's stage runners wait for worker results with `queue.get(timeout=1)` and
only notice a stage has finished after a get times out, so every stage idles
for up to a second after its work is done: ~8 of the ~14 seconds MFA takes on
one short clip. Shorten those polling timeouts. Only calls made directly from
MFA's code are affected; anything else keeps its real timeout.

Remove once MFA stops polling (or once we align in a long-lived process).
"""
import multiprocessing.queues
import queue
import sys

POLL_TIMEOUT = 0.05  # seconds


def _short_poll(get):
	def wrapper(self, block=True, timeout=None):
		if timeout is not None and timeout > POLL_TIMEOUT:
			caller = sys._getframe(1).f_globals.get('__name__', '')
			if caller.startswith('montreal_forced_aligner'):
				timeout = POLL_TIMEOUT
		return get(self, block, timeout)
	return wrapper


queue.Queue.get = _short_poll(queue.Queue.get)
multiprocessing.queues.Queue.get = _short_poll(multiprocessing.queues.Queue.get)
