#!/usr/bin/env python3
import json
import os
import logging
from time import sleep
import requests
import string
from datetime import datetime
import sys
import subprocess
import random
import time
import json
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.utils import helpers
from subprocess import call
from DbConnector import DbConnector
import asyncio
from telethon import TelegramClient

#Check if the given path is an absolute path
def createAbsolutePath(path):
	if not os.path.isabs(path):
		currentDir = os.path.dirname(os.path.realpath(__file__))
		path = os.path.join(currentDir, path)
	return path

# The main class
class Giornalettiere:

	#Load config and psw
	def __init__(self, config, loggingHandler):
		all_settings_dir 	= "Settings"
		file_list_path		= "myFileList.json"
		giornalettiere_db	= "Giornalettiere.db"

		self.config = config
		self.logging = loggingHandler

		#Loading values
		self.localParameters = config['local']
		giornalettiere_db = createAbsolutePath(os.path.join(all_settings_dir,giornalettiere_db))

		#Insert default values
		if not 'json_db' in self.localParameters:
			self.localParameters['json_db'] = False

		#Define File List
		self.db = DbConnector(giornalettiere_db, self.logging)
		self.fileListPath = createAbsolutePath(os.path.join(all_settings_dir,file_list_path))
		self.readFileList()

		#Connecting to Telegram
		self.TmUpdater = Updater(self.localParameters['telegram_token'], use_context=True)
		self.TmDispatcher = self.TmUpdater.dispatcher
		self.bot = self.TmUpdater.bot
		self.logging.info("Connected succesfully to Telegram")


	#Check if new files are present in the directory
	def checkNewFiles(self):
		#Extract list of file from directory, filtering only interesting one (no already uploaded, no wrong file extension)
		newFiles = []
		self.readFileList()
		observedDir = os.path.join(
			self.localParameters['fileLocation'],
			self.localParameters['downloadRequest']
		)
		self.logging.info("checkNewFiles - checking new file in ["+observedDir+"]")
		for root, dirs, files in os.walk(observedDir):
			for file in files:
				#Check file extension
				if file.endswith(tuple(self.localParameters["filetypes"])) :
					#Check if file is new
					if (not file in self.myFileList):
						foundNew = os.path.join(root,file)
						self.logging.info("checkNewFiles - Found new file ["+foundNew+"]")
						newFiles.append(foundNew)
						self.addToFileList(file)
		self.logging.info('File research concluded')
		return newFiles

	#Updates the channel using the new files
	def updateChannel(self, fileFound=""):
		if fileFound:
			self.logging.info("updateChannel - Update triggered by this file ["+fileFound+"]")
		self.logging.info("updateChannel - Start checking for new files")
		newFiles = self.checkNewFiles()
		self.logging.info("updateChannel - Found "+str(len(newFiles))+" new files")
		for newFile in newFiles:
			self.logging.info("updateChannel - The new file is: " + str(newFile))
			#TODO Define a message for each file (es. hashtag, date)
			message = ""
			response = self.sendDocument(
				self.localParameters['myChannel'],
				newFile,
				message
			)
		self.logging.info('updateChannel - Done')

	#Read my file list
	def readFileList(self):
		if self.localParameters['json_db']:
			return self.readJsonFileList()
		else :
			self.myFileList = self.db.getFiles()
			self.logging.info('File list loaded')
			return self.myFileList

	#Read my file list as a json
	def readJsonFileList(self):
		try:
			with open(self.fileListPath) as json_file:
				self.myFileList = json.load(json_file)
		except ValueError:
			self.logging.warning('Cannot decode the stored file list - Using an empty one')
			print("Invalid json ["+str(self.fileListPath)+"] - Use empty one")
			self.myFileList = []
		except FileNotFoundError:
			self.logging.warning('Stored file list not found - Using an empty one')
			print("File list not existent ["+str(self.fileListPath)+"] - Using an empty one")
			self.myFileList = []
		self.logging.info('File list loaded')
		return self.myFileList

	#Updates the file list
	def dumpFileList(self):
		self.storeJsonFileList()

	#Add a file to the file list
	def addToFileList(self, filename):
		filename = str(filename)
		self.myFileList.append(filename)
		if self.localParameters['json_db']:
			self.dumpFileList()
			self.logging.info('Appended to JSON file list ['+str(filename)+']')
		else:
			self.db.insertFile(filename)
			self.logging.info('Appended to DB file list ['+str(filename)+']')

	#Remove a file from the file list
	def removeFromFileList(self, filename):
		filename = str(filename)
		self.logging.info("removeFromFileList - Element before: "+str(len(self.myFileList)))
		self.myFileList.remove(filename)
		self.logging.info("removeFromFileList - Element after: "+str(len(self.myFileList)))
		if self.localParameters['json_db']:
			self.dumpFileList()
		else:
			self.db.removeFile(filename)

	#Updates the json file list
	def storeJsonFileList(self):
		with open(self.fileListPath, "w") as json_file:
				json.dump(self.myfileList, json_file)

	#Enable the deamon to answer to message
	def start(self):
		#Defining handlers
		self.createHandlers()
		self.logging.info("Bot handlers created")
		print("Bot handlers created")
		#Starting bot
		self.TmUpdater.start_polling()
		self.logging.info("Bot is now polling for new messages")

	#Enable the deamon to answer to message
	def stop(self):
		self.TmUpdater.stop()
		self.logging.info("Bot is now stopped")

	#Send the selected message
	def sendMessage(self, message, chat=None, parse_mode=None):
		mex = str(message)[:4095]
		if not chat:
			self.logging.error("Missing chat - Message not sent")
			return
		try:
			self.bot.sendMessage(chat, mex, parse_mode=parse_mode)
		except telegram.error.BadRequest:
			self.logging.error("Cannot send message to chat ["+str(chat)+"] - Skip")
		except telegram.error.Unauthorized:
			self.logging.info("Bot blocked by chat ["+str(chat)+"] - Remove user")
			self.removeFromFileList(chat)

	def sendDocument(self, chat, filePath, message):
		maxSize = 52428800 #50MB - https://core.telegram.org/bots/faq#how-do-i-upload-a-large-file
		maxSize = 0 #Used to debug client
		if os.path.getsize(filePath) < maxSize:
			document = open(filePath, 'rb')
		else:
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			document = loop.run_until_complete(self.sendBigDocument(filePath))
		#Check on size and integration with Telethon
		try:
			return self.bot.send_document(
				chat,
				document,
				caption=message,
				timeout=600,
				disable_notification=False,
				parse_mode=telegram.ParseMode.MARKDOWN_V2
			)
		except telegram.error.BadRequest:
			self.logging.error("sendDocument - BadRequest - Cannot send message to chat ["+str(chat)+"] - Skip")
		except telegram.error.Unauthorized:
			self.logging.info("sendDocument - Bot blocked by chat ["+str(chat)+"] - Remove user")
			self.removeFromFileList(chat)
		except telegram.error:
			self.logging.error("sendDocument - Generic Telegram error")

	#Send the file using the client insted of the bot - Return the reference to the uploaded file
	async def sendBigDocument(self, filePath):
		self.logging.info("Attempting upload using client")
		client = TelegramClient('bot_session', self.localParameters['apiId'], self.localParameters['apiHash'])
		await client.start(bot_token=self.localParameters['telegram_token'],)
		file = await client.upload_file(filePath)
		self.logging.info("sendBigDocument - Requested upload of file")
		self.logging.info("sendBigDocument - Uploaded file: "+file.name+"["+str(file.id)+"]")
		return telegram.Document(str(file.id), file.md5_checksum)

	#Define the approriate handlers
	def createHandlers(self):
		#Commands
		self.TmDispatcher.add_handler(CommandHandler("update", self.updateHandler))
		self.logging.info("createHandlers - Created handlers for command")
		#Text message
		self.TmDispatcher.add_handler(MessageHandler(Filters.text, self.textHandler))
		self.logging.info("createHandlers - Created handlers for text")
		#Errors
		self.TmDispatcher.add_error_handler(self.errorHandler)
		self.logging.info("createHandlers - Created handlers for errors")

	def errorHandler(self, update=None, context=None):
		self.logging.error("errorHandler - unknown error:["+str(context.error)+"]")


	#Handle a received message
	def textHandler(self, update=None, context=None):
		self.logging.info("textHandler - Request from user id ["+str(update.message.chat.id)+"]")

		#Extract all link to download
		originalLinks = update.message.text.strip().split()
		requestedLink = []
		for downloadLink in originalLinks:
			downloadLink = downloadLink.strip()
			if downloadLink.startswith('http'):
				requestedLink.append(downloadLink)

		#Request link
		if len(requestedLink) == len(originalLinks):
			self.logging.info("textHandler - Requested "+str(len(requestedLink))+" link from chat ["+str(update.effective_chat)+"]")
			self.requestDownload(requestedLink)
			update.message.reply_text(
				"Link in download\! 😎 🐱‍💻",
				parse_mode=telegram.ParseMode.MARKDOWN_V2
			)
		else:
			update.message.reply_text(
				"Ciao 🙋\! Il bot al momento è in fase di test, ti notificherò in caso di aggiornamenti",
				parse_mode=telegram.ParseMode.MARKDOWN_V2
			)

	#Send requested link to a download service
	def requestDownload(self, links):
		if isinstance(links, list):
			links = "\n".join(links)

		payload = {'titolo': self.localParameters['downloadRequest'], 'link': links}
		self.logging.info("requestDownload - Request download to my site ["+self.localParameters['downloadSite']+"]")
		r = requests.post(self.localParameters['downloadSite'], data=payload)
		files = links.splitlines()
		self.logging.info("requestDownload - Request download of " + str(len(files)) + " files ["+", ".join(files)+"]")

	#Retrieve data to upload on Telegram
	def fetchData(self):
		#Get data
		self.logging.info("fetchData - Fetching new documents")
		res = subprocess.Popen(["python3", self.localParameters['fetcherScript']], stdout=subprocess.PIPE).communicate()
		#Decode json result
		allResult = json.loads(res[0].decode('ascii').strip())
		result = []
		for f in allResult:
			self.logging.info("fetchData - Fetching "+ str(f))
			if isinstance(f, list) and len(f) == 1:
				f = f[0]
			if 'url' not in f:
				self.logging.info("fetchData - Missing url value "+ str(f))
			else:
				result.append(f['url'])
		self.logging.info("fetchData - Fetched "+ str(len(result)) +" urls")
		#Request download if any link is found
		if len(result):
			self.requestDownload(result)
		return result

	#Search for new file to download
	def updateHandler(self, update=None, context=None):
		self.logging.info("updateHandler - Bot started by: "+str(update.effective_chat))
		result = self.fetchData()
		if len(result):
			update.message.reply_text("Ciao "+ str(update.effective_chat.first_name) +" 👋, sto prelevando dei nuovi file 🛒")
		else:
			update.message.reply_text("Ciao "+ str(update.effective_chat.first_name) +" 👋, non sono riuscito a trovare nulla di nuovo 🕵️")
