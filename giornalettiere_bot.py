#!/usr/bin/env python3
import sys
import os
import logging
import subprocess
import time
import random
import datetime
import time
from telegram.ext import Updater
import json
import requests
from subprocess import call
import schedule
import threading
from Giornalettiere import Giornalettiere
from DirectoryWatcher import DirectoryWatcher

#Check if the given path is an absolute path
def createAbsolutePath(path):
	if not os.path.isabs(path):
		currentDir = os.path.dirname(os.path.realpath(__file__))
		path = os.path.join(currentDir, path)
		
	return path

#Used to run scheduled task as threads
def run_threaded(job_func):
    job_thread = threading.Thread(target=job_func)
    job_thread.start()

#Defining local parameters
all_settings_dir 	= "Settings"
local_path 			= "local_settings.json"
logFile		 		= "Giornalettiere.log"
local_path 			= createAbsolutePath(os.path.join(all_settings_dir, local_path))
logFile 			= createAbsolutePath(logFile)

#Set logging file
#Update log file if needed
logging.basicConfig(filename=logFile,level=logging.ERROR,format='%(asctime)s %(levelname)-8s %(message)s')

#Load config
config = dict()
try:
	path = local_path
	with open(path) as json_file:
		config['local']	= json.load(json_file)
except ValueError:
	print("Cannot load settings - Invalid json ["+str(path)+"]")
	exit()
except FileNotFoundError:
	print("Cannot load settings - Setting file not found ["+str(path)+"]")
	exit()

logging.getLogger().setLevel('INFO')
giorna = Giornalettiere(config, logging)

#On boot action
if len(sys.argv) > 1 and sys.argv[1]=='systemd':
    logging.info("Started by systemd using argument: "+sys.argv[1])

#Schedule actions
# ~ schedule.every(config['local']['refresh_rate']).minutes.do(run_threaded, giorna.updateChannel)
# ~ logging.info("Update every "+str(config['local']['refresh_rate'])+" minutes")
for selected_time in config['local']['dailyChecksAt']:
	try:
		schedule.every().day.at(str(selected_time)).do(run_threaded, giorna.fetchData)
		logging.info("Setting daily check at: "+str(selected_time))
	except schedule.ScheduleValueError as e:
		logging.error("Cannot set a scheduled run at ["+str(selected_time)+"]: "+str(e))
		exit()


#Start bot
giorna.start()
print('Bot started succesfully')
logging.info("Bot started succesfully")

#Add notifier
watched_dir = os.path.join(config['local']['fileLocation'], config['local']['downloadRequest']) 
watcher = DirectoryWatcher(
	watched_dir,
	giorna,
	logging
)
watcher.start()
logging.info("Created notifier succesfully")


while 1:
	time.sleep(1)
	schedule.run_pending()
	if not watcher.is_alive():
		logging.warning("DirectortWatcher is dead, restarting")
		watcher = DirectoryWatcher(
			watched_dir,
			giorna,
			logging
		)
		watcher.start()
		
