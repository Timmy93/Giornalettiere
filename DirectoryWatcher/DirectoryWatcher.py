import asyncio
import logging
import threading
import inotify.adapters
import os
import time


class DirectoryWatcher(threading.Thread):

	def __init__(self, callback_function: callable, async_loop=None):
		# daemon=True: if the main process exits without calling stop()
		# (e.g. a crash), this background thread won't keep the process
		# alive on its own.
		threading.Thread.__init__(self, daemon=True)
		self.async_mode = async_loop is not None
		self.loop = async_loop
		self.watched_events = None
		self.logging = logging.getLogger(__name__)
		self.callbackFunction = callback_function
		self._stop_event = threading.Event()
		self.logging.info("Created DirectoryWatcher element")

	def watch_this_directory(self, directory, events, recursively=False):
		if not os.path.isdir(directory):
			os.makedirs(directory, exist_ok=True)

		if not os.path.isdir(directory):
			self.logging.error("The given directory [" + str(directory) + "] is not a directory")
			raise Exception("The given directory [" + str(directory) + "] is not a directory")

		if events:
			# Consider all events as array
			if type(events) is str:
				events = [events]
			self.watched_events = events
			self.logging.info("Monitoring the following events: [" + str(self.watched_events) + "]")
		else:
			self.logging.info("No events to monitor")
			raise Exception('No events to monitor')

		if recursively:
			self.notifier = inotify.adapters.InotifyTree(directory)
			self.logging.info("Starting a recursive monitoring on directory and subdirectory [" + directory + "]")
		else:
			self.notifier = inotify.adapters.Inotify()
			self.notifier.add_watch(directory)
			self.logging.info("Starting a plain monitoring on directory [" + directory + "]")

	def run(self):
		pending = set()

		while not self._stop_event.is_set():
			try:
				for event in self.notifier.event_gen(yield_nones=True, timeout_s=1):
					if self._stop_event.is_set():
						break
					if event is None:
						continue

					mask = event[1]
					path = os.path.join(event[2], event[3])
					self.logging.info(event)
					# File arrivato nella directory
					if 'IN_CREATE' in mask:
						self.logging.info(f"File appeared: {path}")
						pending.add(path)

					# File chiuso dopo scrittura → pronto
					if 'IN_CLOSE_WRITE' in mask or 'IN_MOVED_TO' in mask :
						if path in pending:
							self.logging.info(f"File ready: {path}")
							pending.remove(path)
						try:
							if self.async_mode:
								if self.loop.is_closed():
									self.logging.error(
										f"Cannot schedule callback for [{path}] - the event loop is closed"
									)
									continue
								future = asyncio.run_coroutine_threadsafe(
									self.callbackFunction(path),
									self.loop
								)
								future.add_done_callback(self._log_callback_result(path))
							else:
								self.callbackFunction(path)
						except FileNotFoundError as err:
							self.logging.warning(f"File missing [{path}] - Skipping callback [{err}]")

			except Exception as err:
				self.logging.exception(f"Unexpected error in DirectoryWatcher loop [{err}]")
				time.sleep(1)

		self.logging.info("DirectoryWatcher - Thread stopped")

	def _log_callback_result(self, path):
		def _callback(future):
			exc = future.exception()
			if exc is not None:
				self.logging.error(f"Callback for file [{path}] raised an exception: {exc}")
		return _callback

	def stop(self):
		"""
		Signal the watcher thread to terminate. run() checks this flag at
		least once per second (see the timeout_s=1 in event_gen above), so
		the thread will exit shortly after this is called - it does not
		join() automatically, call self.join() afterwards if you need to
		block until the thread has actually terminated.
		:return: None
		"""
		self.logging.info("DirectoryWatcher - Stop requested")
		self._stop_event.set()


	@staticmethod
	def stable_size(my_file):
		"""
		Check if the file is still being written
		:param my_file: The file to control
		:return: True if the file has not changed size during last second. False otherwise
		"""
		initial_size = os.path.getsize(my_file)
		time.sleep(1)
		return os.path.getsize(my_file) == initial_size