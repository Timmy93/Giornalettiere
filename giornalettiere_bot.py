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
	filename = os.path.abspath(os.path.join(os.path.dirname(str(__file__)), config_dir, config.get(log_section, {}).get(log_file_field, default_log_file)))
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

async def main():
	config_dir = "Settings"
	config_file_name = 'local_settings.toml'
	configFile = os.path.abspath(os.path.join(os.path.dirname(str(__file__)), config_dir, config_file_name))

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
	loop = asyncio.get_running_loop()
	watcher = None
	try:
		watched_dir = os.path.join(config['Download']['fileLocation'], config['Download']['downloadRequest'])
		watcher = DirectoryWatcher(giorna.update_channel, loop)
		watcher.watch_this_directory(watched_dir, ['IN_CREATE', 'IN_MOVED_TO', 'IN_CLOSE_WRITE'])
		watcher.start()
		logger.info("Created notifier successfully")
	except Exception as err:
		logger.error("Cannot setup the notifier ["+str(err)+"]")
		print("Cannot setup the notifier ["+str(err)+"]")
		print("Exiting")
		exit(1)

	# Start bot (blocks - via an internal asyncio.Event - until stopped)
	logger.info("Starting Giornalettiere Bot")
	print("Starting Giornalettiere Bot")
	try:
		await giorna.start()
	except Exception as err:
		logger.exception(f"Bot crashed: {err}")
		print(f"Bot crashed: {err}")
	finally:
		await giorna.stop()
		if watcher is not None:
			watcher.stop()
		print("Exiting")

if __name__ == '__main__':
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass