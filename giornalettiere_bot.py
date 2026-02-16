#!/usr/bin/env python3
import asyncio
import sys
import os
import logging
from Giornalettiere import Giornalettiere, load_config, MissingConfigException
from DirectoryWatcher.DirectoryWatcher import DirectoryWatcher

def initialize_log(config, config_dir="Settings"):
	"""
    Initialize log file
    :return:
    """
	log_section = "General"
	packages_section = "Packages"
	log_file_field, default_log_file = "logFile",  "Giornalettiere.log"
	log_level_field, default_log_level = "logLevel", "DEBUG"
	filename = os.path.abspath(os.path.join(os.path.dirname(__file__), config_dir, config.get(log_section, {}).get(log_file_field, default_log_file)))
	log_level = config.get(log_section, {}).get(log_level_field, default_log_level)

	logging.basicConfig(
		level=log_level,
		format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
		handlers=[
			logging.FileHandler(filename, mode="a"),
		]
	)
	for package in config.get(packages_section, []):
		name = package.get('name')
		level = package.get('log_level', log_level)
		logging.getLogger(name).setLevel(level)
	logger = logging.getLogger("main")
	return logger

def main():
	config_dir = "Settings"
	config_file_name = 'local_settings.toml'
	configFile = os.path.abspath(os.path.join(os.path.dirname(__file__), config_dir, config_file_name))

	try:
		# Load config
		config = load_config(configFile)
		logger = initialize_log(config, config_dir)
		#Create bot class
		giorna = Giornalettiere(config, config_dir)
	except MissingConfigException as exc:
		print(f"Cannot load config: [{configFile}] - Error: {exc}")
		logging.error(f"Cannot load config: [{configFile}] - Error: {exc}")
		exit()
	except Exception as exc:
		print(f"Critical error during startup: {exc}")
		logging.exception(f"Critical error during startup: {exc}")
		exit()

	# On boot action
	if len(sys.argv) > 1 and sys.argv[1] == 'systemd':
		logger.info("Started by systemd using argument: "+sys.argv[1])

	# Add notifier
	try:
		watched_dir = os.path.join(config['Download']['fileLocation'], config['Download']['downloadRequest'])
		watcher = DirectoryWatcher(giorna.update_channel, asyncio.get_event_loop())
		watcher.watch_this_directory(watched_dir, ['IN_CREATE', 'IN_MOVED_TO', 'IN_CLOSE_WRITE'])
		watcher.start()
		logger.info("Created notifier successfully")

		# Start bot
		logger.info("Starting Giornalettiere Bot")
		print("Starting Giornalettiere Bot")
		giorna.start()

	except Exception as err:
		logger.error("Cannot setup the notifier ["+str(err)+"]")
		print("Cannot setup the notifier ["+str(err)+"]")
		giorna.stop()
		print("Exiting")
		exit(1)

if __name__ == '__main__':
	main()