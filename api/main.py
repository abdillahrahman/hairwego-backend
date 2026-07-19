import os
import shutil
from utils.image_compress import compress_and_save, compress_cv2_image
import cv2
from facenet_pytorch import MTCNN as FaceNetMTCNN
import numpy as np
from datetime import datetime
from flask import Blueprint, request, jsonify
from PIL import Image, ExifTags
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import NoAuthorizationError
import torch
from transformers import ViTForImageClassification, ViTImageProcessor
import tensorflow as tf
from tensorflow.keras.applications.resnet50 import preprocess_input as resnet_preprocess

from extensions import db
from models import (
    FaceShape,
    ScanResult,
    HairType,
    HaircutRecommendation,
    UserRecommendationHistory,
    User,
    Haircut,
    TryOnHistory,
)
import logging
from functools import wraps


api_bp = Blueprint("api", __name__)

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


# Load ViT face shape model once at startup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIT_MODEL_PATH = os.path.join(BASE_DIR, "face-shape-classifier")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
vit_model = ViTForImageClassification.from_pretrained(VIT_MODEL_PATH)
vit_model.to(device)
vit_model.eval()
vit_processor = ViTImageProcessor.from_pretrained(VIT_MODEL_PATH)

print(f"[INFO] ViT face shape model loaded on: {device}")

# Load ResNet50 hair type model once at startup
HAIR_TYPE_MODEL_PATH = os.path.join(BASE_DIR, "hair-type-classifier", "model_final_resnet_50.keras")
HAIR_TYPE_CLASSES = ['curly', 'kinky', 'straight', 'wavy']
HAIR_TYPE_IMG_SIZE = (224, 224)

hair_type_model_keras = tf.keras.models.load_model(HAIR_TYPE_MODEL_PATH)

print(f"[INFO] ResNet50 hair type model loaded from: {HAIR_TYPE_MODEL_PATH}")

UPLOAD_FOLDER = "static/uploads/"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "tiff", "webp", "jfif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def correct_image_orientation(image_path):
    try:
        img = Image.open(image_path)

        exif = img._getexif()
        if exif is not None:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == "Orientation":
                    break

            exif_orientation = exif.get(orientation)
            if exif_orientation == 3:
                img = img.rotate(180, expand=True)
            elif exif_orientation == 6:
                img = img.rotate(270, expand=True)
            elif exif_orientation == 8:
                img = img.rotate(90, expand=True)


        img.save(image_path)
        img.close()
    except Exception as e:
        print(f"Failed to correct orientation: {e}")

detector = FaceNetMTCNN(keep_all=False, device=device)

def detect_face_and_crop(image_path):
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        return None, "Failed to read image."

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(image_rgb)
    boxes, _ = detector.detect(img_pil)

    if boxes is None or len(boxes) == 0:
        return None, "No face detected."

    x1, y1, x2, y2 = [int(b) for b in boxes[0]]
    x1 = max(0, x1)
    y1 = max(0, y1)
    w = x2 - x1
    h = y2 - y1

    enlarge_factor = 1.3
    center_x = x1 + w // 2
    
    # Kembalikan ke normal agar AI tetap akurat
    center_y = y1 + h // 2 
    
    new_w = int(w * enlarge_factor)
    new_h = int(h * enlarge_factor)
    new_x = max(0, center_x - new_w // 2)
    new_y = max(0, center_y - new_h // 2)
    new_x2 = min(image_rgb.shape[1], new_x + new_w)
    new_y2 = min(image_rgb.shape[0], new_y + new_h)

    cropped_face = image_rgb[new_y:new_y2, new_x:new_x2]
    cropped_bgr = cv2.cvtColor(cropped_face, cv2.COLOR_RGB2BGR)

    return cropped_bgr, None

def crop_and_save(image_path):
    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        return None, "Failed to read image."

    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(image_rgb)
    boxes, _ = detector.detect(img_pil)

    if boxes is None or len(boxes) == 0:
        return None, "No face detected."

    x1, y1, x2, y2 = [int(b) for b in boxes[0]]
    x1 = max(0, x1)
    y1 = max(0, y1)
    w = x2 - x1
    h = y2 - y1

    enlarge_factor = 1.3
    center_x = x1 + w // 2
    center_y = y1 + h // 2
    new_w = int(w * enlarge_factor)
    new_h = int(h * enlarge_factor)

    # Tambah top_offset untuk mengambil lebih banyak rambut
    top_offset = int(0.35 * h) 
    
    # Kurangi bottom_offset agar crop bawahnya (dagu/leher) naik
    bottom_offset = int(0.05 * h) 
    
    left_offset = int(0.2 * w)
    right_offset = int(0.2 * w)

    new_y = max(0, center_y - new_h // 2 - top_offset)
    new_x = max(0, center_x - new_w // 2 - left_offset)
    
    # Perhitungan lebar dan tinggi yang baru
    new_x2 = min(image_rgb.shape[1], new_x + new_w + left_offset + right_offset)
    new_y2 = min(image_rgb.shape[0], new_y + new_h + top_offset + bottom_offset)

    cropped_face = image_rgb[new_y:new_y2, new_x:new_x2]
    cropped_bgr = cv2.cvtColor(cropped_face, cv2.COLOR_RGB2BGR)

    return cropped_bgr, None


@api_bp.route("/predict", methods=["POST"])
@log_access("predict")
def predict():
    if "file" not in request.files:
        return jsonify({"message": "No image in the request"}), 400

    files = request.files.getlist("file")
    filename = "temp_image.png"
    errors = {}
    success = False

    for file in files:
        if file and allowed_file(file.filename):
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            success = True
        else:
            errors["message"] = f"File type of {file.filename} is not allowed"

    if not success:
        return jsonify(errors), 400

    img_path = os.path.join(UPLOAD_FOLDER, filename)
    correct_image_orientation(img_path)

    timestamp = datetime.now().strftime("%d%m%y-%H%M%S")
    with Image.open(img_path) as im:
        if im.width > im.height:
            im = im.rotate(90, expand=True)
        saved_path = compress_and_save(im, os.path.join(UPLOAD_FOLDER, f"{timestamp}.jpg"))

    # Crop wajah untuk disimpan (extended crop)
    cropped_face_extend, error_message = crop_and_save(saved_path)
    if cropped_face_extend is None:
        return jsonify({"message": error_message}), 400
    cropped_path_extend = compress_cv2_image(cropped_face_extend, os.path.join(UPLOAD_FOLDER, f"cropped_extend_{timestamp}.jpg"))

    # Crop wajah untuk prediksi (tight crop)
    cropped_face, error_message = detect_face_and_crop(saved_path)
    if cropped_face is None:
        return jsonify({"message": error_message}), 400
    cropped_path = compress_cv2_image(cropped_face, os.path.join(UPLOAD_FOLDER, f"cropped_{timestamp}.jpg"))

    # --- Prediksi Face Shape dengan ViT ---
    img = Image.open(cropped_path).convert("RGB")
    inputs = vit_processor(images=img, return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = vit_model(**inputs)
        logits = outputs.logits
        probabilities = torch.nn.functional.softmax(logits, dim=-1)
        predicted_idx = probabilities.argmax(-1).item()
        face_confidence = probabilities[0][predicted_idx].item()

    predicted_face_shape = vit_model.config.id2label[predicted_idx]  # "oval", "round", "square"

    face_shape_probs = {}
    for i, prob in enumerate(probabilities[0]):
        label = vit_model.config.id2label[i]
        face_shape_probs[label] = f"{prob.item() * 100:.2f}%"


    # --- Prediksi Hair Type dengan ResNet50 (pakai gambar asli) ---
    img_full = Image.open(saved_path).convert("RGB")
    img_resized = img_full.resize(HAIR_TYPE_IMG_SIZE)
    img_array = np.array(img_resized, dtype=np.float32)
    img_array = resnet_preprocess(img_array)
    img_batch = np.expand_dims(img_array, axis=0)

    hair_predictions = hair_type_model_keras.predict(img_batch, verbose=0)
    hair_predicted_idx = int(np.argmax(hair_predictions[0]))
    hair_confidence = float(hair_predictions[0][hair_predicted_idx])

    predicted_hair_type = HAIR_TYPE_CLASSES[hair_predicted_idx]

    hair_type_probs = {}
    for i, prob in enumerate(hair_predictions[0]):
        label = HAIR_TYPE_CLASSES[i]
        hair_type_probs[label] = f"{float(prob) * 100:.2f}%"


    # Cek apakah user login
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except NoAuthorizationError:
        user_id = None

    haircut_list = []

    # Ambil face shape dan hair type dari DB
    face_shape = FaceShape.query.filter_by(shape_name=predicted_face_shape).first()
    if not face_shape:
        return jsonify({"message": "Face shape not found in database"}), 404

    hair_type = HairType.query.filter_by(type_name=predicted_hair_type).first()
    if not hair_type:
        return jsonify({"message": "Hair type not found in database"}), 404

    # Ambil rekomendasi berdasarkan kombinasi face shape + hair type
    recommendations = HaircutRecommendation.query.filter_by(
        face_shape_id=face_shape.id,
        hair_type_id=hair_type.id
    ).all()
    
    if not recommendations:
        return jsonify({
            "face_shape": predicted_face_shape,
            "face_shape_confidence": f"{face_confidence * 100:.2f}%",
            "hair_type": predicted_hair_type,
            "hair_type_confidence": f"{hair_confidence * 100:.2f}%",
            "message": "No recommendations found for this face shape and hair type combination"}), 404

    # Simpan ke DB hanya jika user login
    scan_result_id_str = None
    if user_id:
        user = User.query.get(user_id)
        if not user:
            return jsonify({"message": "User not found"}), 404

        new_scan = ScanResult(
            user_id=user.id,
            image_path=saved_path,
            image_path_cropped=cropped_path_extend,
            face_shape_id=face_shape.id,
            hair_type_id=hair_type.id,
            face_shape_probabilities=face_shape_probs,
            hair_type_probabilities=hair_type_probs,
        )
        db.session.add(new_scan)
        db.session.commit()
        scan_result_id_str = str(new_scan.id)

        for recommendation in recommendations:
            history = UserRecommendationHistory(
                user_id=user.id,
                haircut_recommendation_id=recommendation.id,
                scan_result_id=new_scan.id,
            )
            db.session.add(history)

        db.session.commit()

    # Format hasil untuk semua user (login dan guest)
    for recommendation in recommendations:
        haircut = recommendation.haircut
        haircut_list.append(
            {
                "haircut_id": haircut.id,
                "haircut_name": haircut.haircut_name,
                "description": haircut.description,
                "image_path": haircut.image_path,
            }
        )

    return (
        jsonify(
            {
                "scan_result_id": scan_result_id_str,
                "face_shape": predicted_face_shape,
                "face_shape_confidence": f"{face_confidence * 100:.2f}%",
                "face_shape_probabilities": face_shape_probs,
                "hair_type": predicted_hair_type,
                "hair_type_confidence": f"{hair_confidence * 100:.2f}%",
                "hair_type_probabilities": hair_type_probs,
                "image_scan": saved_path,
                "rekomendasi": haircut_list,
                "mode": "user" if user_id else "guest",
            }
        ),
        200,
    )


@api_bp.route("/history", methods=["GET"])
@log_access("get_history")
@jwt_required()
def get_history():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    # Query ScanResult and group by scan_date
    scan_results = (
        ScanResult.query.filter_by(user_id=user_id)
        .order_by(ScanResult.scan_date.desc())
        .all()
    )

    history = {}
    for scan in scan_results:
        scan_date = scan.scan_date.to('Asia/Jakarta').format("YYYY-MM-DD HH:mm:ss")
        if scan_date not in history:
            history[scan_date] = []

        # Get recommendations for the current scan
        recommendations = UserRecommendationHistory.query.filter_by(
            scan_result_id=scan.id
        ).all()
        recommendation_details = []
        for recommendation in recommendations:
            haircut_recommendation = recommendation.haircut_recommendation
            if haircut_recommendation and haircut_recommendation.haircut:
                haircut = haircut_recommendation.haircut
                recommendation_details.append(
                    {
                        "haircut_id": haircut.id,
                        "haircut_name": haircut.haircut_name, 
                        "description": haircut.description,
                        "image_path": haircut.image_path,
                    }
                )

        # Get try-on results for this scan
        tryon_results = TryOnHistory.query.filter_by(
            scan_result_id=scan.id
        ).order_by(TryOnHistory.created_at.desc()).all()

        tryon_details = []
        for tryon in tryon_results:
            tryon_details.append({
                "tryon_id": str(tryon.id),
                "haircut_id": str(tryon.haircut_id),
                "haircut_name": tryon.haircut.haircut_name if tryon.haircut else "N/A",
                "result_image": tryon.result_image_path,
                "created_at": tryon.created_at.to('Asia/Jakarta').format("YYYY-MM-DD HH:mm:ss"),
            })

        history[scan_date].append(
            {
                "scan_result_id": str(scan.id),
                "scan_date": scan_date,
                "scan_image": scan.image_path,
                "scan_image_cropped": scan.image_path_cropped,
                "face_shape": scan.face_shape.shape_name if scan.face_shape else "N/A",
                "face_shape_probabilities": scan.face_shape_probabilities or {},
                "hair_type": scan.hair_type.type_name if scan.hair_type else "N/A",
                "hair_type_probabilities": scan.hair_type_probabilities or {},
                "recommendations": recommendation_details,
                "tryon_results": tryon_details,
            }
        )

    return jsonify(history), 200

@api_bp.route("/history/<int:scan_result_id>", methods=["DELETE"])
@jwt_required()
def delete_history(scan_result_id):
    user_id = get_jwt_identity()

    scan_result = ScanResult.query.filter_by(id=scan_result_id, user_id=user_id).first()
    if not scan_result:
        return jsonify({"message": "History not found or unauthorized"}), 404

    # Hapus semua rekomendasi terkait
    UserRecommendationHistory.query.filter_by(scan_result_id=scan_result_id).delete()

    # Hapus semua try-on history terkait
    TryOnHistory.query.filter_by(scan_result_id=scan_result_id).delete()

    # Hapus scan_result
    db.session.delete(scan_result)
    db.session.commit()

    return jsonify({"message": "History deleted successfully"}), 200


@api_bp.route("/tryon-history", methods=["GET"])
@jwt_required()
@log_access("get_tryon_history")
def get_tryon_history():
    """Get all try-on history for the current user (including standalone try-ons)."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    tryons = TryOnHistory.query.filter_by(
        user_id=user_id
    ).order_by(TryOnHistory.created_at.desc()).all()

    result = []
    for tryon in tryons:
        result.append({
            "tryon_id": str(tryon.id),
            "scan_result_id": str(tryon.scan_result_id) if tryon.scan_result_id else None,
            "haircut_id": str(tryon.haircut_id),
            "haircut_name": tryon.haircut.haircut_name if tryon.haircut else "N/A",
            "result_image": tryon.result_image_path,
            "created_at": tryon.created_at.to('Asia/Jakarta').format("YYYY-MM-DD HH:mm:ss"),
        })

    return jsonify(result), 200


@api_bp.route("/profile", methods=["GET"])
@jwt_required()
@log_access("get_profile")
def get_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"message": "User not found"}), 404
    
    scan_count = ScanResult.query.filter_by(user_id=user_id).count()
    
    latest_scan = ScanResult.query.filter_by(user_id=user_id).order_by(ScanResult.scan_date.desc()).first()
    latest_face_shape = latest_scan.face_shape.shape_name if latest_scan else None
    
    return jsonify({
        "fullname": user.full_name,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.format("YYYY-MM-DD HH:mm:ss"),
        "total_scans": scan_count,
        "latest_face_shape": latest_face_shape
    }), 200

