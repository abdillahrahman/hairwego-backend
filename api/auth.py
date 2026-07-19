from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
from extensions import db
from models import User
import logging
from functools import wraps

auth_bp = Blueprint("auth", __name__)

logging.basicConfig(
    filename='access.log', 
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

def log_access(route_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = None
            try:
                user_id = get_jwt_identity()
            except Exception:
                pass
            logging.info(
                f"Route: {route_name} | User: {user_id} | Method: {request.method} | Path: {request.path} | IP: {request.remote_addr}"
            )
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route("/register", methods=["POST"])
@log_access("register")
def register():
    data = request.json
    fullname = data.get("fullname")
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if User.query.filter_by(username=username).first():
        return jsonify({"message": "Username already exists"}), 409

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "Email already registered"}), 409

    new_user = User(
        full_name=fullname,
        username=username,
        email=email,
        password=generate_password_hash(password),
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201


@auth_bp.route("/login", methods=["POST"])
@log_access("login")
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "Email not found"}), 404
    
    if not check_password_hash(user.password, password):
        return jsonify({"message": "Incorrect password"}), 401

    user_id = str(user.id)
    access_token = create_access_token(identity=user_id)
    refresh_token = create_refresh_token(identity=user_id)
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token
    }), 200


@auth_bp.route("/refresh-token", methods=["POST"])
@jwt_required(refresh=True)
@log_access("refresh_token")
def refresh_token():    
    current_user = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user)
    return jsonify({"access_token": new_access_token}), 200
