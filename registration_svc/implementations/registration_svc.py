from flask import Flask
from registration_svc.interfaces.registration_interface import RegistrationInterface, RegistrationDAO
from pymongo import MongoClient
from dotenv import load_dotenv
import os

app = Flask(__name__)
load_dotenv()

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
