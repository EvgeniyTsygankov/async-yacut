import os


class Config:
    SQLALCHEMY_DATABASE_URI = (
        os.getenv('DATABASE_URI') or os.getenv('DB') or 'sqlite:///yacut.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
    DISK_TOKEN = os.getenv('DISK_TOKEN', '')
    DISK_BASE_DIR = os.getenv('DISK_BASE_DIR', 'app:/yacut')