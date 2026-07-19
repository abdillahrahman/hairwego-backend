"""
Try-On route for hairstyle visualization.

Uses OpenRouter's Gemini image generation API to visualize a recommended
hairstyle on the user's photo. The flow:
1. Receive user selfie + hairstyle_id
2. Preprocess user image (face detection, crop, resize)
3. Load & prepare hairstyle reference image
4. Send both to OpenRouter with a carefully crafted prompt
5. Return the generated visualization
"""

import os
import io
import base64
import logging
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import NoAuthorizationError
from PIL import Image
from functools import wraps
from utils.image_compress import compress_and_save

from extensions import db
from models import Haircut, TryOnHistory, User
from api.preprocessing import detect_and_crop_face, prepare_reference_image

tryon_bp = Blueprint("tryon", __name__)

logger = logging.getLogger(__name__)

# Constants
UPLOAD_FOLDER = "static/uploads/"
TRYON_FOLDER = "static/uploads/tryon/"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "tiff", "webp", "jfif"}

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/images"
OPENROUTER_MODEL = "google/gemini-3.1-flash-lite-image"


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
                f"Route: {route_name} | User: {user_id} | Method: {request.method} "
                f"| Path: {request.path} | IP: {request.remote_addr}"
            )
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _pil_to_base64_data_url(img: Image.Image, fmt: str = "PNG") -> str:
    """Convert a PIL Image to a base64-encoded data URL string."""
    buffer = io.BytesIO()
    img.save(buffer, format=fmt)
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    mime = f"image/{fmt.lower()}"
    return f"data:{mime};base64,{b64}"


def _build_tryon_prompt(hairstyle_name: str) -> str:
    """
    Build a carefully crafted prompt for the hairstyle try-on visualization.

    The prompt instructs the model to:
    - Transfer ONLY the hairstyle from the reference to the user's photo
    - Preserve the user's face, skin tone, facial features exactly
    - Maintain realistic lighting, proportions, and natural appearance
    """
    return (
        f"You are a professional hairstyle visualization tool. "
        f"I am providing two images:\n"
        f"- Image 1: A person's portrait photo (the user)\n"
        f"- Image 2: A reference hairstyle photo showing the '{hairstyle_name}' hairstyle\n\n"
        f"Generate a new realistic photo of the SAME person from Image 1, but with their hair "
        f"changed to match the '{hairstyle_name}' hairstyle shown in Image 2.\n\n"
        f"CRITICAL RULES:\n"
        f"- Keep the person's face, facial features, skin tone, and expression EXACTLY the same\n"
        f"- ONLY change the hairstyle to match the reference\n"
        f"- Match the hair color, length, texture, and styling from the reference\n"
        f"- Maintain realistic lighting consistent with the original photo\n"
        f"- The result should look like a natural, unedited photograph\n"
        f"- Maintain the same camera angle and framing as the original portrait\n"
        f"- The hair should blend naturally with the person's head and face shape"
    )


@tryon_bp.route("/try-on", methods=["POST"])
@log_access("try_on")
def try_on():
    """
    Generate a hairstyle try-on visualization.

    Accepts a user selfie and a hairstyle_id, preprocesses both images,
    then uses OpenRouter's Gemini API to generate the visualization.

    Request (multipart/form-data):
        - user_image: Image file (the user's selfie/portrait)
        - hairstyle_id: UUID of the haircut to try on

    Response:
        - result_image: Path to the generated visualization
        - hairstyle_name: Name of the applied hairstyle
    """
    # --- Validate API key ---
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY not configured")
        return jsonify({
            "status": "error",
            "message": "Try-on service is not configured. Please contact the administrator."
        }), 503

    # --- Validate request ---
    if "user_image" not in request.files:
        return jsonify({
            "status": "error",
            "message": "No user image provided. Please upload a photo."
        }), 400

    hairstyle_id = request.form.get("hairstyle_id")
    if not hairstyle_id:
        return jsonify({
            "status": "error",
            "message": "No hairstyle_id provided. Please select a hairstyle."
        }), 400

    user_image = request.files["user_image"]
    if not user_image or not allowed_file(user_image.filename):
        return jsonify({
            "status": "error",
            "message": f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    # --- Look up hairstyle from database ---
    haircut = Haircut.query.get(hairstyle_id)
    if not haircut:
        return jsonify({
            "status": "error",
            "message": "Hairstyle not found. Please select a valid hairstyle."
        }), 404

    if not haircut.image_path:
        return jsonify({
            "status": "error",
            "message": "Hairstyle reference image is not available."
        }), 404

    # --- Ensure output directories exist ---
    os.makedirs(TRYON_FOLDER, exist_ok=True)

    timestamp = datetime.now().strftime("%d%m%y-%H%M%S")

    # --- Save and preprocess user image ---
    temp_user_path = os.path.join(UPLOAD_FOLDER, f"tryon_input_{timestamp}.png")
    try:
        user_image.save(temp_user_path)
    except Exception as e:
        logger.error(f"Failed to save user image: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to save the uploaded image."
        }), 500

    try:
        user_img_processed = detect_and_crop_face(
            temp_user_path,
            output_size=1024,
            top_margin_ratio=0.70,
            side_margin_ratio=0.30,
            bottom_margin_ratio=0.05,
        )
    except ValueError as e:
        # Clean up temp file
        if os.path.exists(temp_user_path):
            os.remove(temp_user_path)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400
    finally:
        # Clean up temp input file (we have the processed version now)
        if os.path.exists(temp_user_path):
            os.remove(temp_user_path)

    # --- Prepare hairstyle reference image ---
    hairstyle_image_path = haircut.image_path
    # Handle relative paths (stored in DB as "static/uploads/haircuts/...")
    if not os.path.isabs(hairstyle_image_path):
        hairstyle_image_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            hairstyle_image_path,
        )

    if not os.path.exists(hairstyle_image_path):
        return jsonify({
            "status": "error",
            "message": "Hairstyle reference image file not found on server."
        }), 404

    try:
        ref_img_processed = prepare_reference_image(hairstyle_image_path, output_size=1024)
    except ValueError as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to process reference image: {str(e)}"
        }), 500

    # --- Convert images to base64 data URLs ---
    user_b64_url = _pil_to_base64_data_url(user_img_processed)
    ref_b64_url = _pil_to_base64_data_url(ref_img_processed)

    # --- Build prompt ---
    prompt = _build_tryon_prompt(haircut.haircut_name)

    # --- Call OpenRouter API ---
    payload = {
        "model": OPENROUTER_MODEL,
        "prompt": prompt,
        "input_references": [
            {"type": "image_url", "image_url": {"url": user_b64_url}},
            {"type": "image_url", "image_url": {"url": ref_b64_url}},
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        logger.info(f"Calling OpenRouter API for try-on (hairstyle: {haircut.haircut_name})")
        response = requests.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=120,  # Image generation can take a while
        )
    except requests.exceptions.Timeout:
        return jsonify({
            "status": "error",
            "message": "Image generation timed out. Please try again."
        }), 504
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenRouter API request failed: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to connect to the image generation service."
        }), 502

    if response.status_code != 200:
        logger.error(
            f"OpenRouter API error: status={response.status_code}, "
            f"body={response.text[:500]}"
        )
        return jsonify({
            "status": "error",
            "message": "Image generation service returned an error. Please try again later.",
            "detail": response.json().get("error", {}).get("message", "Unknown error")
            if response.headers.get("content-type", "").startswith("application/json")
            else "Unknown error",
        }), 502

    # --- Parse and save the generated image ---
    try:
        result = response.json()
        images_data = result.get("data", [])

        if not images_data:
            return jsonify({
                "status": "error",
                "message": "No image was generated. Please try again."
            }), 502

        # Take the first generated image
        image_b64 = images_data[0].get("b64_json")
        if not image_b64:
            return jsonify({
                "status": "error",
                "message": "Generated image data is empty."
            }), 502

        image_bytes = base64.b64decode(image_b64)

        # Save the result with compression
        result_filename = f"tryon_{timestamp}.jpg"
        result_path = os.path.join(TRYON_FOLDER, result_filename)

        # Load from bytes, compress, and save
        tryon_image = Image.open(io.BytesIO(image_bytes))
        result_path = compress_and_save(tryon_image, result_path)

    except (ValueError, KeyError) as e:
        logger.error(f"Failed to parse OpenRouter response: {e}")
        return jsonify({
            "status": "error",
            "message": "Failed to process the generated image."
        }), 502

    scan_result_id = request.form.get("scan_result_id")

    # --- Save try-on history if user is logged in ---
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except NoAuthorizationError:
        user_id = None

    tryon_history_id = None
    if user_id:
        user = User.query.get(user_id)
        if user:
            tryon_record = TryOnHistory(
                user_id=user.id,
                scan_result_id=scan_result_id if scan_result_id else None,
                haircut_id=haircut.id,
                result_image_path=result_path,
            )
            db.session.add(tryon_record)
            db.session.commit()
            tryon_history_id = str(tryon_record.id)
            logger.info(f"Try-on history saved: {tryon_record.id}")

    # --- Return success response ---
    return jsonify({
        "status": "success",
        "tryon_history_id": tryon_history_id,
        "scan_result_id": scan_result_id,
        "result_image": result_path,
        "hairstyle_name": haircut.haircut_name,
        "message": "Try-on visualization generated successfully",
    }), 200
