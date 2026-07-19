import os
from datetime import timedelta

SECRET_KEY = "123456790"

SQLALCHEMY_DATABASE_URI = "mysql+pymysql://root:1111@localhost/hairwego"
SQLALCHEMY_TRACK_MODIFICATIONS = False
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "super-secret-key")

# Expired time
JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)

# OpenRouter API key for hairstyle try-on visualization
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")




