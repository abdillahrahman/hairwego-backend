from .main import api_bp
from .auth import auth_bp
from .tryon import tryon_bp

def init_api(app):
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(tryon_bp, url_prefix="/api")
