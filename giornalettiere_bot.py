#!/usr/bin/env python3
import sys
import os
import logging
import time
import json
import tomllib
from datetime import datetime, timedelta

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


def calculate_new_time(start_time_str, delay_minutes):
	start_time = datetime.strptime(start_time_str, "%H:%M")
	delay = timedelta(minutes=int(delay_minutes))
	new_time = start_time + delay
	# Return the new time as a string in the same format
	return new_time.strftime("%H:%M")


# Defining local parameters
all_settings_dir = "Settings"
local_path = "local_settings.toml"
logFile = "Giornalettiere.log"
local_path = create_absolute_path(os.path.join(all_settings_dir, local_path))
logFile = create_absolute_path(os.path.join(all_settings_dir, logFile))

# Set logging file
# Update log file if needed
logging.basicConfig(filename=logFile, level=logging.ERROR, format='%(asctime)s %(levelname)-8s %(message)s')

# Load config
try:
	with open(local_path, "rb") as f:
		config = tomllib.load(f)
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
delay = config["Download"].get("recheckDelay", 0)
for selected_time in config['Download']['dailyChecksAt']:
	try:
		schedule.every().day.at(str(selected_time)).do(run_threaded, giorna.fetch_data)
		logging.info("Setting daily check at: "+str(selected_time))
		if delay:
			manual_recheck = calculate_new_time(selected_time, delay)
			schedule.every().day.at(manual_recheck).do(run_threaded, giorna.update_channel)
			logging.info("Planned manual recheck at: " + str(manual_recheck))
	except schedule.ScheduleValueError as e:
		logging.error("Cannot set a scheduled run at ["+str(selected_time)+"]: "+str(e))
		exit()


# Start bot
giorna.start()
print('Bot started successfully')
logging.info("Bot started successfully")

# Add notifier
try:
	watched_dir = os.path.join(config['Download']['fileLocation'], config['Download']['downloadRequest'])
	watcher = DirectoryWatcher(giorna.update_channel, logging)
	watcher.watch_this_directory(watched_dir, ['IN_CREATE', 'IN_MOVED_TO'])
	watcher.start()
	logging.info("Created notifier successfully")

	while 1:
		try:
			time.sleep(1)
			schedule.run_pending()
			if not watcher.is_alive():
				logging.warning("DirectoryWatcher is dead, restarting")
				watcher = DirectoryWatcher(giorna.update_channel, logging)
				watcher.watch_this_directory(watched_dir, ['IN_CREATE', 'IN_MOVED_TO'])
				watcher.start()
		except Exception as err:
			logging.exception("Unexpected error during bot execution - Stop bot")
			exit(1)

except Exception as err:
	logging.error("Cannot setup the notifier ["+str(err)+"]")
	print("Cannot setup the notifier ["+str(err)+"]")
	giorna.stop()
	exit(1)
		
