import os
from flask import Flask
from jinja2 import StrictUndefined
from flask_cors import CORS

from extensions import db, jwt, login_manager
from admin import init_admin
from api import init_api

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile("config.py")

    # Init extensions
    db.init_app(app)
    jwt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin_auth.login"
    login_manager.login_message = "Silakan login untuk mengakses halaman admin."
    login_manager.login_message_category = "warning"

    # User loader for flask-login (admin users only)
    @login_manager.user_loader
    def load_user(user_id):
        from models import AdminUser
        return AdminUser.query.get(user_id)

    # Enable CORS
    CORS(app)

    # Register Blueprints
    init_admin(app)
    init_api(app)

    app.jinja_env.undefined = StrictUndefined
    
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
