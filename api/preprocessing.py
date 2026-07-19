"""
Face detection and image preprocessing for hairstyle try-on.

Uses MediaPipe for face detection with automatic API version detection
(legacy mp.solutions vs newer mp.tasks). Provides functions to:
- Detect and crop face with generous margins (for hair + face + neck framing)
- Prepare reference hairstyle images (resize/pad to square)
"""

import os
import urllib.request
import cv2
import numpy as np
import mediapipe as mp
from PIL import Image
import logging

logger = logging.getLogger(__name__)

# Auto-detect MediaPipe API version
_USE_LEGACY_MP = hasattr(mp, "solutions")

if _USE_LEGACY_MP:
    mp_face_detection = mp.solutions.face_detection
    logger.info("[Preprocessing] Using legacy MediaPipe face detection API")
else:
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    _MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
    _MODEL_PATH = os.path.join(_MODEL_DIR, "blaze_face_short_range.tflite")
    if not os.path.exists(_MODEL_PATH):
        logger.info("[Preprocessing] Downloading blaze_face_short_range.tflite...")
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/"
            "face_detector/blaze_face_short_range/float16/1/"
            "blaze_face_short_range.tflite",
            _MODEL_PATH,
        )
    _face_detector_options = mp_vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=_MODEL_PATH),
        min_detection_confidence=0.5,
    )
    logger.info("[Preprocessing] Using mp.tasks MediaPipe face detection API")


def _detect_face_box_legacy(img_rgb, w, h):
    """Detect face bounding box using legacy MediaPipe API."""
    with mp_face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    ) as detector:
        results = detector.process(img_rgb)
    if not results.detections:
        return None
    best = max(results.detections, key=lambda d: d.score[0])
    bbox = best.location_data.relative_bounding_box
    return bbox.xmin * w, bbox.ymin * h, bbox.width * w, bbox.height * h


def _detect_face_box_tasks(img_rgb, w, h):
    """Detect face bounding box using newer mp.tasks API."""
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
    with mp_vision.FaceDetector.create_from_options(_face_detector_options) as detector:
        result = detector.detect(mp_image)
    if not result.detections:
        return None
    best = max(result.detections, key=lambda d: d.categories[0].score)
    bbox = best.bounding_box
    return bbox.origin_x, bbox.origin_y, bbox.width, bbox.height


def detect_and_crop_face(
    image_path: str,
    output_size: int = 1024,
    top_margin_ratio: float = 0.70,
    side_margin_ratio: float = 0.30,
    bottom_margin_ratio: float = 0.05,
) -> Image.Image:
    """
    Detect face then crop with proportional margins for portrait framing
    (hair + face + slight neck/shoulders), then resize to output_size x output_size.

    The default ratios are calibrated for hairstyle visualization: generous top
    margin to capture full hairstyle, moderate side margins, minimal bottom.

    Args:
        image_path: Path to the input image file.
        output_size: Output square dimension in pixels.
        top_margin_ratio: Space above face relative to face height (captures hair).
        side_margin_ratio: Space left/right relative to face width.
        bottom_margin_ratio: Space below face relative to face height (captures chin/neck).

    Returns:
        PIL Image cropped and resized to output_size x output_size.

    Raises:
        ValueError: If image cannot be read or no face is detected.
    """
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise ValueError(f"Failed to read image: {image_path}")

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, _ = img_rgb.shape

    if _USE_LEGACY_MP:
        box = _detect_face_box_legacy(img_rgb, w, h)
    else:
        box = _detect_face_box_tasks(img_rgb, w, h)

    if box is None:
        raise ValueError("No face detected in the image.")

    fx, fy, fw, fh = box

    # Calculate margins based on face dimensions
    top_pad = fh * top_margin_ratio
    bottom_pad = fh * bottom_margin_ratio
    side_pad = fw * side_margin_ratio

    x1 = fx - side_pad
    y1 = fy - top_pad
    x2 = fx + fw + side_pad
    y2 = fy + fh + bottom_pad

    # Make crop square based on the largest side, centered on face
    box_w = x2 - x1
    box_h = y2 - y1
    side = max(box_w, box_h)

    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    x1 = cx - side / 2
    x2 = cx + side / 2
    y1 = cy - side / 2
    y2 = cy + side / 2

    # Clamp to image bounds, shift box to stay square & within frame
    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > w:
        x1 -= x2 - w
        x2 = w
    if y2 > h:
        y1 -= y2 - h
        y2 = h

    x1 = max(0, int(round(x1)))
    y1 = max(0, int(round(y1)))
    x2 = min(w, int(round(x2)))
    y2 = min(h, int(round(y2)))

    cropped = img_rgb[y1:y2, x1:x2]
    pil_img = Image.fromarray(cropped)
    pil_img = pil_img.resize((output_size, output_size), Image.LANCZOS)

    return pil_img


def prepare_reference_image(image_path: str, output_size: int = 1024) -> Image.Image:
    """
    Prepare a hairstyle reference image by resizing to a square.

    Unlike user photos, reference images are already curated hairstyle photos.
    We only resize/pad to match the expected input dimensions without cropping
    to preserve the full hairstyle context.

    Args:
        image_path: Path to the reference hairstyle image.
        output_size: Output square dimension in pixels.

    Returns:
        PIL Image resized to output_size x output_size.

    Raises:
        ValueError: If image cannot be read.
    """
    img = Image.open(image_path).convert("RGB")
    if img is None:
        raise ValueError(f"Failed to read reference image: {image_path}")

    # Resize with aspect ratio preservation + padding to square
    img.thumbnail((output_size, output_size), Image.LANCZOS)

    # If already square after thumbnail, return directly
    if img.size[0] == output_size and img.size[1] == output_size:
        return img

    # Pad to square with white background
    padded = Image.new("RGB", (output_size, output_size), (255, 255, 255))
    paste_x = (output_size - img.size[0]) // 2
    paste_y = (output_size - img.size[1]) // 2
    padded.paste(img, (paste_x, paste_y))

    return padded


def preprocess_for_tryon(input_path: str, output_path: str, output_size: int = 1024) -> str:
    """
    Wrapper: detect face, crop, resize, and save to output_path.

    Args:
        input_path: Path to the input user image.
        output_path: Path to save the preprocessed image.
        output_size: Output square dimension in pixels.

    Returns:
        The output_path where the preprocessed image was saved.
    """
    from utils.image_compress import compress_and_save
    pil_img = detect_and_crop_face(input_path, output_size=output_size)
    return compress_and_save(pil_img, output_path)
