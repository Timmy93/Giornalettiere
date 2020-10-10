#!/usr/bin/env python3
import threading
import inotify.adapters
import logging
import os
import time

# The main class
class DirectoryWatcher (threading.Thread):
   
	def __init__(self, observedDirectory, bot, logging):
		threading.Thread.__init__(self)
		self.logging = logging
		self.bot = bot
		self.notifier = inotify.adapters.Inotify()
		self.notifier.add_watch(observedDirectory)
		self.logging.info("Started watching directory ["+observedDirectory+"]")
   
	def run(self):
		while(1):
			try:
				for event in self.notifier.event_gen():
					if event is not None:
						# ~ print(event)
						if 'IN_CREATE' in event[1] or 'IN_MOVED_TO' in event[1]:
							newfile = os.path.join(event[2], event[3])
							self.logging.info("Created/moved a file/directory ["+newfile+"]")
							while not self.stableSize(newfile):
								self.logging.info("Still writing on file ["+newfile+"]")
								#TODO check that file has been completely written, do not wait 1 seconds and recheck 
							self.bot.updateChannel()
				self.logging.warning("DirectoryWatcher stopped checking directory")
			except RuntimeError:
				self.logging.warning("Thread is dead for a Runtime error, restarting")
			else:
				self.logging.warning("Thread is dead, restarting")
	
	#Check if the file is still being written
	def stableSize(self, myFile):
		initialSize = os.path.getsize(myFile)
		time.sleep(1)
		return os.path.getsize(myFile) == initialSize
