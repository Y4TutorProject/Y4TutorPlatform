from flask import Flask
from registration_interface import RegistrationInterface, RegistrationDAO
from pymongo import MongoClient
from dotenv import load_dotenv
import os

app = Flask(__name__)
load_dotenv()

class MongoDAO(RegistrationDAO):
    connection_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME")

    def __init__(self):
        self.client = MongoClient(self.connection_uri)
        self.db = self.client[self.db_name]

    def connect_to_database(self):
        if self.client.admin.command('ping'):
            print("Connected to MongoDB")
            return True
        return False

    def add_to_database(self, data):
        self.connect_to_database()
        if self.client.insert_one(data):
            return True
        return False    

    def update_database(self, data):
        self.connect_to_database()
        if self.client.update_one(data):
            return True
        return False

class RegistrationService(RegistrationInterface):
    def __init__(self):
        self.app = Flask(__name__)
        self.dao = MongoDAO()

    def register_user(self, user_data):
        self.dao.add_to_database(user_data)

    def validate_user(self, user_data):
        pass

    def log_in_user(self, user_data):
        pass
