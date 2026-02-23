import os
import logging
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail

# Import db and bcrypt from models to avoid duplicate instances
from core.models import db, bcrypt

# Initialize other extensions
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"
