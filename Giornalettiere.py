#!/usr/bin/env python3
import os
import tomllib
import requests
import json
import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from DbConnector import DbConnector
from telethon import TelegramClient
from GiornalettiereDownloader import GiornalettiereDownloader
from DirectoryWatcher.DirectoryWatcher import DirectoryWatcher


# Check if the given path is an absolute path
def create_absolute_path(path: str):
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
        self.logging = logging_handler

        # Loading values
        self.localParameters = config
        giornalettiere_db = create_absolute_path(os.path.join(all_settings_dir, giornalettiere_db))

        # Insert default values
        if 'json_db' not in self.localParameters['Download']:
            self.localParameters['Download']['json_db'] = False
        if 'debug_useOnlyClient' not in self.localParameters['Telegram']:
            self.localParameters['Telegram']['debug_useOnlyClient'] = False

        # Define File List
        self.db = DbConnector(giornalettiere_db, self.logging)
        self.fileListPath = create_absolute_path(os.path.join(all_settings_dir, file_list_path))
        self.read_file_list()

        # Connecting to Telegram
        self.application = Application.builder().token(self.localParameters['Telegram']['telegram_token']).build()
        self.bot = self.application.bot
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
            self.localParameters['Download']['fileLocation'],
            self.localParameters['Download']['downloadRequest']
        ))
        self.logging.info("checkNewFiles - checking new file in [" + observed_dir + "]")
        for root, dirs, files in os.walk(observed_dir):
            for file in files:
                # Check file extension
                if file.endswith(tuple(self.localParameters['Download']["filetypes"])):
                    # Check if file is new
                    if file not in self.myFileList:
                        found_new = os.path.join(root, file)
                        self.logging.info("checkNewFiles - Found new file [" + found_new + "]")
                        new_files.append(found_new)
                        self.add_to_file_list(file)
        self.logging.info('File research concluded')
        return new_files

    async def update_channel(self, file_found=""):
        """
        Updates the channel sending new files
        :param file_found: The file that has triggered the update
        :return: None
        """
        if file_found:
            self.logging.info("update_channel - Update triggered by this file [" + file_found + "]")
        self.logging.info("update_channel - Start checking for new files")
        new_files = self.check_new_files()
        self.logging.info("update_channel - Found " + str(len(new_files)) + " new files")
        while new_files:
            # Attempts to send only completed files
            new_files = list(set(new_files) - set(await self.send_file_list(new_files)))
            self.logging.info("update_channel - Waiting to send " + str(len(new_files)) + " new files")
        self.logging.info('update_channel - Done')

    async def send_file_list(self, file_list):
        """
        Attempt to send the completed files
        :param file_list: The complete list of files to send
        :return: The list of sent files
        """
        sent_files = []
        for newFile in file_list:
            # Wait for new file
            if DirectoryWatcher.stable_size(newFile):
                self.logging.info("update_channel - The new file is: " + str(newFile))
                # TODO Define a message for each file (es. hashtag, date)
                message = ""
                await self.send_document(
                    self.localParameters['Telegram']['myChannel'],
                    newFile,
                    message
                )
                sent_files.append(newFile)
        return sent_files

    def read_file_list(self):
        """
        Read my file list
        :return: The list of already managed files
        """
        if self.localParameters['Download']['json_db']:
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
        if self.localParameters['Download']['json_db']:
            self.dump_file_list()
            self.logging.info('Appended to JSON file list [' + str(filename) + ']')
        else:
            self.db.insertFile(filename)
            self.logging.info('Appended to DB file list [' + str(filename) + ']')

    def remove_from_file_list(self, filename: str):
        """
        Remove a file from the file list  of already managed
        :param filename: The file to remove from the list of already managed
        :return: None
        """
        filename = str(filename)
        self.logging.info("removeFromFileList - Element before: " + str(len(self.myFileList)))
        self.myFileList.remove(filename)
        self.logging.info("removeFromFileList - Element after: " + str(len(self.myFileList)))
        if self.localParameters['Download']['json_db']:
            self.dump_file_list()
        else:
            self.db.removeFile(filename)

    def start(self):
        """
        Enable the daemon to answer to message
        :return:  None
        """
        # Defining handlers
        self.create_handlers()
        self.logging.info("Bot handlers created")
        print("Bot handlers created")
        # Starting bot
        self.application.run_polling()
        self.logging.info("Bot is now polling for new messages")

    def stop(self):
        """
        Stop the daemon
        :return: None
        """
        self.application.stop()
        self.logging.info("Bot is now stopped")

    async def send_message(self, message, chat=None, parse_mode=None):
        """
        Send a text message on the Telegram chat
        :param message: The message to send
        :param chat: The chat to use
        :param parse_mode: The message parse method
        :return: None
        """
        mex = str(message)[:4095]
        if not chat:
            self.logging.error("Missing chat - Message not sent")
            return
        try:
            await self.bot.send_message(chat_id=chat, text=mex, parse_mode=parse_mode)
        except telegram.error.BadRequest:
            self.logging.error("Cannot send message to chat [" + str(chat) + "] - Skip")
        except telegram.error.Forbidden:
            self.logging.info("Bot blocked by chat [" + str(chat) + "] - Remove user")
            self.remove_from_file_list(chat)

    async def send_document(self, chat, file_path, message):
        """
        Wrapper function used to send the file according to its size
        :param chat: The chat id the file will be sent to
        :param file_path: The file to send
        :param message: The message to send with the file
        :return: None
        """
        max_size = 52428800  # 50MB - https://core.telegram.org/bots/faq#how-do-i-upload-a-large-file
        if os.path.getsize(file_path) >= max_size or self.localParameters['Telegram']['debug_useOnlyClient']:
            self.logging.info("send_document - Sending big document using telethon library")
            # loop = asyncio.new_event_loop()
            # asyncio.set_event_loop(loop)
            # loop.run_until_complete(self.send_big_document(file_path, message, chat))
            await self.send_big_document(file_path, message, chat)
        else:
            await self.send_small_document(file_path, message, chat)
        self.logging.info("send_document - Document sent")

    async def send_small_document(self, file_path, message, chat):
        """
        Send file using canonical bot API
        :param file_path: The file to send
        :param message: The message to send with the file
        :param chat: The chat id the file will be sent to
        :return:
        """
        try:
            with open(file_path, 'rb') as document:
                await self.bot.send_document(
                    chat_id=chat,
                    document=document,
                    caption=message,
                    disable_notification=False,
                    parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
                )
                self.logging.info(f"send_small_document - File sent [{file_path}]")
        except telegram.error.BadRequest as err:
            self.logging.error(
                f"send_small_document - BadRequest - Cannot send message to chat [{chat}][{err}] - Skip")
        except telegram.error.Forbidden:
            self.logging.info(f"send_small_document - Bot blocked by chat [{chat}] - Remove user")
            self.remove_from_file_list(chat)
        except Exception as e:  # Usa Exception invece di telegram.error (che non è un'eccezione)
            self.logging.error(f"send_small_document - Generic error: {e}")

    async def send_big_document(self, file_path, message, chat):
        """
        Send the file using the client instead of the bot
        :param file_path: The file to send
        :param message: The message to send with the file
        :param chat: The chat id the file will be sent to
        :return: None
        """
        try:
            self.logging.info("Attempting upload using client")
            session_file = create_absolute_path(os.path.join(self.settingDir, 'bot_session.session'))
            await self.connect_to_telegram_client(session_file)
            # Assicurati che il client sia connesso
            if not self.client.is_connected():
                self.logging.info("Client not connected, connecting now")
                await self.client.connect()

                # Se necessario, effettua il login
                if not await self.client.is_user_authorized():
                    self.logging.warning("Client not authorized, authentication needed")
                    # Implementa la logica di autenticazione se necessario
                    # Questo passaggio potrebbe richiedere intervento umano

            chat = self.get_chat_parsed(chat)
            self.logging.debug("Attempting sending message to chat [" + str(chat) + "] with message [" + message + "]")
            # Gestisci potenziali errori di connessione
            try:
                msg1 = await self.client.send_message(chat, 'Nuovo giornale in arrivo...')
                self.logging.debug(
                    f"Attempting sending [{file_path}] to chat [{chat}] with message [{message}]")
                await self.client.send_file(chat, file_path, caption=message)
                self.logging.info(f"sendBigDocument - File sent [{file_path}]")
                await self.client.delete_messages(chat, msg1)
                self.logging.debug("sendBigDocument - Deleted previous message")
            except Exception as e:
                self.logging.error(f"Error during file sending with Telethon: {e}")
                # Fallback a send_small_document se necessario
                await self.send_small_document(file_path, message, chat)
                # Logout e pulizia
                await self.client.log_out()
                delattr(self, 'client')
        except Exception as e:
            self.logging.error(f"Overall error in send_big_document: {e}")
            # Fallback a send_small_document
            self.logging.info("Falling back to send_small_document")
            await self.send_small_document(file_path, message, chat)

    def get_chat_parsed(self, chat_id):
        """
        Parse the chat from String to Integer
        :param chat_id: The chat code to parse
        :return: The chat code parsed
        """
        if chat_id[0] == '-':
            self.logging.info("Parsing string as negative integer")
            chat_id = int(chat_id)
        return chat_id

    def callback(self, current, total):
        """
        Callback function to print the upload progress
        :param current: The sent bytes
        :param total: The total bytes to send
        :return: None
        """
        print('Uploaded', current, 'out of', total, 'bytes: {:.2%}'.format(current / total))

    async def connect_to_telegram_client(self, session_name):
        """
        Connect to telegram client
        :param session_name: The session name used to connect
        :return: None
        """
        if not hasattr(self, 'client'):
            self.client = TelegramClient(session_name, self.localParameters['Telegram']['apiId'],
                                         self.localParameters['Telegram']['apiHash'])
            self.logging.info("Created client instance")
            await self.client.start(bot_token=self.localParameters['Telegram']['telegram_token'])
            self.logging.info("Client restarted")
        else:
            if not self.client.is_connected():
                self.logging.info("Connecting client")
                await self.client.connect()

    def create_handlers(self):
        """
        Creates all the appropriate handlers to manage different messages/commands/errors
        :return:  None
        """
        # Commands
        self.application.add_handler(CommandHandler("update", self.update_handler))
        self.application.add_handler(CommandHandler("news", self.news_handler))
        self.logging.info("createHandlers - Created handlers for command")
        # Text message
        # self.application.add_handler(MessageHandler(filters.TEXT, self.text_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))

        self.logging.info("createHandlers - Created handlers for text")
        # Errors
        self.application.add_error_handler(self.error_handler)
        self.logging.info("createHandlers - Created handlers for errors")

    def error_handler(self, update=None, context=None):
        """
        The handler to manage errors
        :param update: The reference to message update
        :param context: The details on the received error
        :return: None
        """
        self.logging.error("error_handler - unknown error:[" + str(context.error) + "]")

    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        The handler to manage text messages
        :param update: The reference to message update
        :param context: The details on the received error
        :return: None
        """
        if not update.message:
            return

        chat_id = update.effective_chat.id
        self.logging.info(f"text_handler - Request from user id [{chat_id}]")

        # Extract all links to download
        original_links = update.message.text.strip().split()
        requested_link = [link.strip() for link in original_links if link.strip().startswith("http")]

        if len(requested_link) == len(original_links):
            self.logging.info(f"text_handler - Requested {len(requested_link)} link(s) from chat [{chat_id}]")
            self.request_download(requested_link)  # Assumo che questa funzione sia definita nella classe
            await update.message.reply_text(
                "Link in download\\! 😎 🐱‍💻",
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
            )
        else:
            await update.message.reply_text(
                "Ciao 🙋\\! Il bot al momento è in fase di test, ti notificherò in caso di aggiornamenti",
                parse_mode=telegram.constants.ParseMode.MARKDOWN_V2
            )

    def request_download(self, links):
        """
        Send requested link to a download service
        :param links: The list of links to download
        :return: None
        """
        if isinstance(links, list):
            links_text = "\n".join(links)
        elif isinstance(links, str):
            links_text = links
        else:
            self.logging.warning("request_download - Expected list or string - Reveived: " + type(links))
            links_text = ""

        payload = {'titolo': self.localParameters['Download']['downloadRequest'], 'link': links_text}
        self.logging.info(
            "request_download - Request download to my site [" + self.localParameters['Download']['downloadSite'] + "]")
        requests.post(self.localParameters['Download']['downloadSite'], data=payload)
        files = links_text.splitlines()
        self.logging.info(
            "request_download - Request download of " + str(len(files)) + " files [" + ", ".join(files) + "]")

    # Retrieve data to upload on Telegram
    def fetch_data(self):
        result = []
        # Get data
        self.logging.info("fetch_data - Fetching new documents")
        print("fetch_data - Fetching new documents")
        downloadConfigDir = "DownloadConfig"
        downloadConfigFiles = os.listdir(downloadConfigDir)
        for filename in downloadConfigFiles:
            if filename.endswith(".toml"):
                with open(os.path.join(downloadConfigDir, filename), "rb") as f:
                    downloadConfig = tomllib.load(f)
                gd = GiornalettiereDownloader(self.logging, downloadConfig)
                output = gd.extractRelevantLinks()
                # Decode json result
                if not output:
                    self.logging.warning("fetch_data - Cannot fetch any data")
                else:
                    result = []
                    for out in output:
                        result.append(out['url'])
                # Request download if any link is found
                if len(result):
                    self.request_download(result)
                return result
        if not downloadConfigFiles:
            self.logging.warning("fetch_data - No download configuration files found - Skip any search")
            return []

    # Search for new file to download
    async def update_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.logging.info("update_handler - Bot started by: " + str(update.effective_chat))
        result = self.fetch_data()
        if len(result):
            await update.message.reply_text(
                "Ciao " + str(update.effective_chat.first_name) + " 👋, sto prelevando dei nuovi file 🛒")
        else:
            await update.message.reply_text(
                "Ciao " + str(update.effective_chat.first_name) + " 👋, non sono riuscito a trovare nulla di nuovo 🕵️")

    async def news_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handles the /news command and checks for updates.
        """
        if not update.effective_chat:
            return

        chat = update.effective_chat
        self.logging.info(f"news_handler - Bot started by: {chat}")

        await update.message.reply_text(
            f"Ciao {chat.first_name} 👋, controllo se ci sono novità 📰"
        )

        await self.update_channel()
