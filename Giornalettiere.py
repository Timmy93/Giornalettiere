#!/usr/bin/env python3
import os
import requests
import subprocess
import json
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from DbConnector import DbConnector
import asyncio
from telethon import TelegramClient


# Check if the given path is an absolute path
def create_absolute_path(path):
	if not os.path.isabs(path):
		current_dir = os.path.dirname(os.path.realpath(__file__))
		path = os.path.join(current_dir, path)
	return path


class Giornalettiere:

	client: TelegramClient
	"""
	The Telegram client used to upload files bigger than 50MB
	"""

	myFileList: list
	"""
	The list of files already managed
	"""

	def __init__(self, config, logging_handler):
		"""
		Load config and psw
		:param config: The configuration object
		:param logging_handler: A logging instance
		"""
		all_settings_dir = "Settings"
		file_list_path = "myFileList.json"
		giornalettiere_db = "Giornalettiere.db"

		self.settingDir = all_settings_dir
		self.config = config
		self.logging = logging_handler

		# Loading values
		self.localParameters = config['local']
		giornalettiere_db = create_absolute_path(os.path.join(all_settings_dir, giornalettiere_db))

		# Insert default values
		if 'json_db' not in self.localParameters:
			self.localParameters['json_db'] = False

		# Define File List
		self.db = DbConnector(giornalettiere_db, self.logging)
		self.fileListPath = create_absolute_path(os.path.join(all_settings_dir, file_list_path))
		self.read_file_list()

		# Connecting to Telegram
		self.TmUpdater = Updater(self.localParameters['telegram_token'], use_context=True)
		self.TmDispatcher = self.TmUpdater.dispatcher
		self.bot = self.TmUpdater.bot
		self.logging.info("Connected successfully to Telegram")

	def check_new_files(self):
		"""
		Check if new files are present in the directory
		:return: The list of file from directory.<br>
				Filtered only interesting (no already uploaded, no wrong file extension)
		"""
		new_files = []
		self.read_file_list()
		observed_dir = str(os.path.join(
			self.localParameters['fileLocation'],
			self.localParameters['downloadRequest']
		))
		self.logging.info("checkNewFiles - checking new file in [" + observed_dir + "]")
		for root, dirs, files in os.walk(observed_dir):
			for file in files:
				# Check file extension
				if file.endswith(tuple(self.localParameters["filetypes"])):
					# Check if file is new
					if file not in self.myFileList:
						found_new = os.path.join(root, file)
						self.logging.info("checkNewFiles - Found new file [" + found_new + "]")
						new_files.append(found_new)
						self.add_to_file_list(file)
		self.logging.info('File research concluded')
		return new_files

	# Updates the channel using the new files
	def update_channel(self, file_found=""):
		if file_found:
			self.logging.info("update_channel - Update triggered by this file [" + file_found + "]")
		self.logging.info("update_channel - Start checking for new files")
		new_files = self.check_new_files()
		self.logging.info("update_channel - Found " + str(len(new_files)) + " new files")
		for newFile in new_files:
			self.logging.info("update_channel - The new file is: " + str(newFile))
			# TODO Define a message for each file (es. hashtag, date)
			message = ""
			self.send_document(
				self.localParameters['myChannel'],
				newFile,
				message
			)
		self.logging.info('update_channel - Done')

	def read_file_list(self):
		"""
		Read my file list
		:return: The list of already managed files
		"""
		if self.localParameters['json_db']:
			return self.read_json_file_list()
		else:
			self.myFileList = self.db.getFiles()
			self.logging.info('File list loaded from DB')
			return self.myFileList

	def read_json_file_list(self):
		"""
		Read my file list as a json
		:return: The list of already managed files
		"""
		try:
			with open(self.fileListPath) as json_file:
				self.myFileList = json.load(json_file)
		except ValueError:
			self.logging.warning('Cannot decode the stored file list - Using an empty one')
			print("Invalid json [" + str(self.fileListPath) + "] - Use empty one")
			self.myFileList = []
		except FileNotFoundError:
			self.logging.warning('Stored file list not found - Using an empty one')
			print("File list not existent [" + str(self.fileListPath) + "] - Using an empty one")
			self.myFileList = []
		self.logging.info('File list loaded')
		return self.myFileList

	def dump_file_list(self):
		"""
		Updates the file list stored in the json
		:return: None
		"""
		with open(self.fileListPath, "w") as json_file:
			json.dump(self.myFileList, json_file)

	def add_to_file_list(self, filename: str):
		"""
		Add a file to the file list
		:param filename: Add a new file to the list of already managed
		:return: None
		"""
		filename = str(filename)
		self.myFileList.append(filename)
		if self.localParameters['json_db']:
			self.dump_file_list()
			self.logging.info('Appended to JSON file list [' + str(filename) + ']')
		else:
			self.db.insertFile(filename)
			self.logging.info('Appended to DB file list [' + str(filename) + ']')

	def remove_from_file_list(self, filename: str):
		"""
		Remove a file from the file list  of already managed
		:param filename: The file to remove from the list of already managed
		:return:
		"""
		filename = str(filename)
		self.logging.info("removeFromFileList - Element before: " + str(len(self.myFileList)))
		self.myFileList.remove(filename)
		self.logging.info("removeFromFileList - Element after: " + str(len(self.myFileList)))
		if self.localParameters['json_db']:
			self.dump_file_list()
		else:
			self.db.removeFile(filename)

	# Enable the deamon to answer to message
	def start(self):
		# Defining handlers
		self.create_handlers()
		self.logging.info("Bot handlers created")
		print("Bot handlers created")
		# Starting bot
		self.TmUpdater.start_polling()
		self.logging.info("Bot is now polling for new messages")

	# Enable the deamon to answer to message
	def stop(self):
		self.TmUpdater.stop()
		self.logging.info("Bot is now stopped")

	# Send the selected message
	def send_message(self, message, chat=None, parse_mode=None):
		mex = str(message)[:4095]
		if not chat:
			self.logging.error("Missing chat - Message not sent")
			return
		try:
			self.bot.send_message(chat, mex, parse_mode=parse_mode)
		except telegram.error.BadRequest:
			self.logging.error("Cannot send message to chat [" + str(chat) + "] - Skip")
		except telegram.error.Unauthorized:
			self.logging.info("Bot blocked by chat [" + str(chat) + "] - Remove user")
			self.remove_from_file_list(chat)

	def send_document(self, chat, file_path, message):
		"""
		Wrapper function used to send the file according to its size
		:param chat: The chat id the file will be sent to
		:param file_path: The file to send
		:param message: The message to send with the file
		:return: None
		"""
		max_size = 52428800  # 50MB - https://core.telegram.org/bots/faq#how-do-i-upload-a-large-file
		if os.path.getsize(file_path) >= max_size or self.localParameters['debug_useOnlyClient']:
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			loop.run_until_complete(self.send_big_document(file_path, message, chat))
		else:
			self.send_small_document(file_path, message, chat)
		self.logging.info("send_document - Document sent")

	def send_small_document(self, file_path, message, chat):
		"""
		Send file using canonical bot API
		:param file_path: The file to send
		:param message: The message to send with the file
		:param chat: The chat id the file will be sent to
		:return:
		"""
		document = open(file_path, 'rb')
		try:
			self.bot.send_document(
				chat,
				document,
				caption=message,
				timeout=600,
				disable_notification=False,
				parse_mode=telegram.ParseMode.MARKDOWN_V2
			)
			self.logging.info("send_small_document - File sent [" + file_path + "]")
		except telegram.error.BadRequest as err:
			self.logging.error(
				"send_small_document - BadRequest - Cannot send message to chat [" + str(chat) + "][" + str(
					err) + "] - Skip")
		except telegram.error.Unauthorized:
			self.logging.info("send_small_document - Bot blocked by chat [" + str(chat) + "] - Remove user")
			self.remove_from_file_list(chat)
		except telegram.error:
			self.logging.error("send_small_document - Generic Telegram error")

	# Send the file using the client instead of the bot
	async def send_big_document(self, file_path, message, chat):
		self.logging.info("Attempting upload using client")
		session_file = create_absolute_path(os.path.join(self.settingDir, 'bot_session.session'))
		await self.connect_to_telegram_client(session_file)
		# await self.client.send_file(chat, filePath, caption=message, progress_callback=self.callback)
		self.logging.debug("Attempting sending message to chat ["+chat+"] with message ["+message+"]")
		msg1 = await self.client.send_message(chat, 'Nuovo giornale in arrivo...')
		self.logging.debug("Attempting sending ["+file_path+"] to chat ["+chat+"] with message ["+message+"]")
		await self.client.send_file(chat, file_path, caption=message)
		self.logging.info("sendBigDocument - File sent [" + file_path + "]")
		await self.client.delete_messages(chat, msg1)
		self.logging.debug("sendBigDocument - Deleted previous message")
		await self.client.log_out()
		delattr(self, 'client')

	# Printing upload progress
	def callback(self, current, total):
		print('Uploaded', current, 'out of', total, 'bytes: {:.2%}'.format(current / total))

	# Connect to telegram client
	async def connect_to_telegram_client(self, session_name):
		if not hasattr(self, 'client'):
			self.client = TelegramClient(session_name, self.localParameters['apiId'], self.localParameters['apiHash'])
			# await self.client.start(bot_token=self.localParameters['telegram_token'])
			self.logging.info("Created client instance")
			await self.client.start(bot_token=self.localParameters['telegram_token'])
			self.logging.info("Client restarted")
		else:
			if not self.client.is_connected():
				self.logging.info("Connecting client")
				await self.client.connect()

	# Define the appropriate handlers
	def create_handlers(self):
		# Commands
		self.TmDispatcher.add_handler(CommandHandler("update", self.update_handler))
		self.logging.info("createHandlers - Created handlers for command")
		# Text message
		self.TmDispatcher.add_handler(MessageHandler(Filters.text, self.text_handler))
		self.logging.info("createHandlers - Created handlers for text")
		# Errors
		self.TmDispatcher.add_error_handler(self.error_handler)
		self.logging.info("createHandlers - Created handlers for errors")

	def error_handler(self, update=None, context=None):
		self.logging.error("error_handler - unknown error:[" + str(context.error) + "]")

	# Handle a received message
	def text_handler(self, update=None, context=None):
		self.logging.info("text_handler - Request from user id [" + str(update.message.chat.id) + "]")

		# Extract all link to download
		original_links = update.message.text.strip().split()
		requested_link = []
		for download_link in original_links:
			download_link = download_link.strip()
			if download_link.startswith('http'):
				requested_link.append(download_link)

		# Request link
		if len(requested_link) == len(original_links):
			self.logging.info("text_handler - Requested " + str(len(requested_link)) + " link from chat [" + str(
				update.effective_chat) + "]")
			self.request_download(requested_link)
			update.message.reply_text(
				"Link in download! 😎 🐱‍💻",
				parse_mode=telegram.ParseMode.MARKDOWN_V2
			)
		else:
			update.message.reply_text(
				"Ciao 🙋! Il bot al momento è in fase di test, ti notificherò in caso di aggiornamenti",
				parse_mode=telegram.ParseMode.MARKDOWN_V2
			)

	def request_download(self, links):
		"""
		Send requested link to a download service
		:param links: The list of links to download
		:return:
		"""
		if isinstance(links, list):
			links_text = "\n".join(links)
		elif isinstance(links, str):
			links_text = links
		else:
			self.logging.warning("request_download - Expected list or string - Reveived: " + type(links))
			links_text = ""

		payload = {'titolo': self.localParameters['downloadRequest'], 'link': links_text}
		self.logging.info(
			"request_download - Request download to my site [" + self.localParameters['downloadSite'] + "]")
		requests.post(self.localParameters['downloadSite'], data=payload)
		files = links_text.splitlines()
		self.logging.info(
			"request_download - Request download of " + str(len(files)) + " files [" + ", ".join(files) + "]")

	# Retrieve data to upload on Telegram
	def fetch_data(self):
		result = []
		# Get data
		self.logging.info("fetch_data - Fetching new documents")
		output, errors = subprocess.Popen(["python3", self.localParameters['fetcherScript']], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
		# Decode json result
		if output is None:
			self.logging.warning("fetch_data - Cannot fetch any data using this fetcherScript [" + str(
				self.localParameters['fetcherScript']) + "] - Error: [" + str(errors) + "]")
		else:
			try:
				all_result = json.loads(output.decode('ascii').strip())
				for f in all_result:
					self.logging.info("fetchData - Fetching " + str(f))
					if isinstance(f, list) and len(f) == 1:
						f = f[0]
					if 'url' not in f:
						self.logging.info("fetchData - Missing url value " + str(f))
					else:
						result.append(f['url'])
				self.logging.info("fetchData - Fetched " + str(len(result)) + " urls")
			except ValueError as e:
				self.logging.warning("fetchData - Cannot decode response - Failed decode [" + str(e) + "]")
		# Request download if any link is found
		if len(result):
			self.request_download(result)
		return result

	# Search for new file to download
	def update_handler(self, update=None, context=None):
		self.logging.info("update_handler - Bot started by: " + str(update.effective_chat))
		result = self.fetch_data()
		if len(result):
			update.message.reply_text(
				"Ciao " + str(update.effective_chat.first_name) + " 👋, sto prelevando dei nuovi file 🛒")
		else:
			update.message.reply_text(
				"Ciao " + str(update.effective_chat.first_name) + " 👋, non sono riuscito a trovare nulla di nuovo 🕵️")
