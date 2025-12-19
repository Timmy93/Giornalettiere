import asyncio
import logging
import threading
import inotify.adapters
import os
import time


class DirectoryWatcher(threading.Thread):

	def __init__(self, callback_function: callable, async_loop=None):
		threading.Thread.__init__(self)
		self.async_mode = async_loop is not None
		self.loop = async_loop
		self.watched_events = None
		self.logging = logging.getLogger(__name__)
		self.callbackFunction = callback_function
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

		while True:
			try:
				for event in self.notifier.event_gen(yield_nones=False):
					mask = event[1]
					path = os.path.join(event[2], event[3])
					self.logging.info(event)
					# File arrivato nella directory
					if 'IN_MOVED_TO' in mask or 'IN_CREATE' in mask:
						self.logging.info(f"File appeared: {path}")
						pending.add(path)

					# File chiuso dopo scrittura → pronto
					if 'IN_CLOSE_WRITE' in mask:
						if path in pending:
							self.logging.info(f"File ready: {path}")
							pending.remove(path)
							try:
								if self.async_mode:
									asyncio.run_coroutine_threadsafe(
										self.callbackFunction(path),
										self.loop
									)
								else:
									self.callbackFunction(path)
							except FileNotFoundError as err:
								self.logging.warning(f"File missing [{path}] - Skipping callback [{err}]")

			except Exception as err:
				self.logging.exception(f"Unexpected thread death [{err}]")


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
