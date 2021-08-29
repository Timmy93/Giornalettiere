#!/usr/bin/env python3
import sys
import os
import logging
import time
import json
import schedule
import threading
from Giornalettiere import Giornalettiere
from DirectoryWatcher.DirectoryWatcher import DirectoryWatcher


# Check if the given path is an absolute path
def create_absolute_path(path):
	if not os.path.isabs(path):
		current_dir = os.path.dirname(os.path.realpath(__file__))
		path = os.path.join(current_dir, path)
		
	return path


# Used to run scheduled task as threads
def run_threaded(job_func):
	job_thread = threading.Thread(target=job_func)
	job_thread.start()


# Defining local parameters
all_settings_dir = "Settings"
local_path = "local_settings.json"
logFile = "Giornalettiere.log"
local_path = create_absolute_path(os.path.join(all_settings_dir, local_path))
logFile = create_absolute_path(logFile)

# Set logging file
# Update log file if needed
logging.basicConfig(filename=logFile, level=logging.ERROR, format='%(asctime)s %(levelname)-8s %(message)s')

# Load config
config = dict()
try:
	with open(local_path) as json_file:
		config['local'] = json.load(json_file)
except ValueError:
	print("Cannot load settings - Invalid json ["+str(local_path)+"]")
	exit()
except FileNotFoundError:
	print("Cannot load settings - Setting file not found ["+str(local_path)+"]")
	exit()

logging.getLogger().setLevel('INFO')
giorna = Giornalettiere(config, logging)

# On boot action
if len(sys.argv) > 1 and sys.argv[1] == 'systemd':
	logging.info("Started by systemd using argument: "+sys.argv[1])

# Schedule actions
for selected_time in config['local']['dailyChecksAt']:
	try:
		schedule.every().day.at(str(selected_time)).do(run_threaded, giorna.fetch_data)
		logging.info("Setting daily check at: "+str(selected_time))
	except schedule.ScheduleValueError as e:
		logging.error("Cannot set a scheduled run at ["+str(selected_time)+"]: "+str(e))
		exit()


# Start bot
giorna.start()
print('Bot started successfully')
logging.info("Bot started successfully")

# Add notifier
try:
	watched_dir = os.path.join(config['local']['fileLocation'], config['local']['downloadRequest']) 
	watcher = DirectoryWatcher(giorna.update_channel, logging)
	watcher.watchThisDirectory(watched_dir, ['IN_CREATE', 'IN_MOVED_TO'])
	watcher.start()
	logging.info("Created notifier successfully")

	while 1:
		try:
			time.sleep(1)
			schedule.run_pending()
			if not watcher.is_alive():
				logging.warning("DirectoryWatcher is dead, restarting")
				watcher = DirectoryWatcher(giorna.update_channel, logging)
				watcher.watchThisDirectory(watched_dir, ['IN_CREATE', 'IN_MOVED_TO'])
				watcher.start()
		except Exception as err:
			logging.exception("Unexpected error during bot execution - Stop bot")
			exit(1)

except Exception as err:
	logging.error("Cannot setup the notifier ["+str(err)+"]")
	print("Cannot setup the notifier ["+str(err)+"]")
	giorna.stop()
	exit(1)
		
