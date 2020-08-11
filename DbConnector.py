#!/usr/bin/env python3
import sqlite3
import os

# The main class
class DbConnector:
	
	#Load config and psw
	def __init__(self, dbPath, loggingHandler):
		self.dbName = dbPath
		self.logging = loggingHandler
				
		#Initialize db if missing
		if not self.dbExists():
			self.createTables()
			self.logging.info("All tables created")
	
	def dbExists(self):
		return os.path.isfile(self.dbName)

	#Create all tables
	def createTables(self):
		#Start connection
		conn = sqlite3.connect(self.dbName)
		cursor = conn.cursor()
		self.logging.info("Db connected")
		#Create here tables
		self.createFileListTable(cursor)
		#Close connection
		conn.commit()
		conn.close()
		
	#Create the table to store the chat
	def createFileListTable(self, cursor):
		sql = "CREATE TABLE files(file_name varchar(64), UNIQUE(file_name))"
		cursor.execute(sql)

	#Add an element
	def insertFile(self, filename):
		#Start connection
		conn = sqlite3.connect(self.dbName)
		cursor = conn.cursor()
		self.logging.info("Db connected")
		sql = "INSERT OR IGNORE INTO files values(?)"
		if type(filename) is not list:
			filename = [str(filename)]
		cursor.executemany(sql, [filename])
		#Close connection
		conn.commit()
		conn.close()

	#Delete an element
	def removeFile(self, filename):
		#Start connection
		conn = sqlite3.connect(self.dbName)
		cursor = conn.cursor()
		self.logging.info("Db connected")
		#Execute
		sql = "DELETE FROM files where file_name = ?"
		if type(filename) is not list:
			filename = [str(filename)]
		cursor.executemany(sql, [filename])
		#Close connection
		conn.commit()
		conn.close()

	#Retrieve all the users
	def getFiles(self):
		#Start connection
		conn = sqlite3.connect(self.dbName)
		cursor = conn.cursor()
		self.logging.info("Db connected")
		#Execute
		sql = "SELECT * FROM files"
		res = cursor.execute(sql)
		#Create list from query
		c_list = []
		for row in res:
			c_list.append(row[0])
		#Close connection
		conn.commit()
		conn.close()
		return c_list
