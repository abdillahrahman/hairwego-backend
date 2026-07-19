"""
Image compression utility for reducing file sizes before saving to static folder.

Compresses images to JPEG format with quality 85, which is the industry standard
for web images — provides ~70-80% file size reduction while maintaining visual
quality that is nearly indistinguishable from the original.

For PNG inputs (which are lossless and very large), conversion to JPEG alone
typically reduces file size by 5-10x.
"""

import os
import io
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# JPEG quality 85 is the sweet spot:
# - Quality 90-95: nearly lossless, but large files
# - Quality 85: excellent quality, significant compression (industry standard)
# - Quality 70-80: noticeable artifacts on close inspection
DEFAULT_JPEG_QUALITY = 85

# Maximum dimension (width or height) for uploaded images.
# Images larger than this will be resized while maintaining aspect ratio.
# 1920px is Full HD and more than sufficient for mobile app display.
MAX_DIMENSION = 1920


def compress_and_save(image, output_path, quality=DEFAULT_JPEG_QUALITY, max_dimension=MAX_DIMENSION):
    """
    Compress and save an image to the specified path as optimized JPEG.

    Args:
        image: PIL Image object or file path (str) to the source image.
        output_path: Destination path. Extension will be changed to .jpg.
        quality: JPEG quality (1-100). Default 85.
        max_dimension: Max width/height. Images exceeding this are resized.

    Returns:
        str: The actual path where the image was saved (with .jpg extension).
    """
    # Load image if path is given
    if isinstance(image, str):
        image = Image.open(image)

    # Convert to RGB (JPEG doesn't support alpha channel)
    if image.mode in ("RGBA", "P", "LA"):
        # Create white background for transparent images
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        background.paste(image, mask=image.split()[-1] if "A" in image.mode else None)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    # Resize if exceeds max dimension
    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
        logger.info(f"Image resized to {image.size[0]}x{image.size[1]}")

    # Change extension to .jpg
    base, _ = os.path.splitext(output_path)
    output_path = base + ".jpg"

    # Save with optimized JPEG compression
    image.save(
        output_path,
        format="JPEG",
        quality=quality,
        optimize=True,  # Extra pass for optimal Huffman coding
        subsampling=1,   # 4:2:2 chroma subsampling (good balance)
    )

    file_size_kb = os.path.getsize(output_path) / 1024
    logger.info(f"Compressed image saved: {output_path} ({file_size_kb:.1f} KB)")

    return output_path


def compress_existing_file(file_path, quality=DEFAULT_JPEG_QUALITY, max_dimension=MAX_DIMENSION):
    """
    Compress an existing image file in-place (replaces with .jpg version).

    Args:
        file_path: Path to the existing image file.
        quality: JPEG quality (1-100). Default 85.
        max_dimension: Max width/height.

    Returns:
        str: The new file path (with .jpg extension).
    """
    if not os.path.exists(file_path):
        logger.warning(f"File not found for compression: {file_path}")
        return file_path

    original_size = os.path.getsize(file_path) / 1024
    new_path = compress_and_save(file_path, file_path, quality=quality, max_dimension=max_dimension)

    new_size = os.path.getsize(new_path) / 1024
    reduction = ((original_size - new_size) / original_size * 100) if original_size > 0 else 0
    logger.info(
        f"Compressed: {original_size:.1f} KB -> {new_size:.1f} KB "
        f"({reduction:.1f}% reduction)"
    )

    # Remove original if extension changed
    if new_path != file_path and os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"Removed original: {file_path}")

    return new_path


def compress_cv2_image(cv2_image, output_path, quality=DEFAULT_JPEG_QUALITY, max_dimension=MAX_DIMENSION):
    """
    Compress and save a cv2 (numpy array BGR) image.

    Args:
        cv2_image: OpenCV image (numpy array in BGR format).
        output_path: Destination path.
        quality: JPEG quality (1-100). Default 85.
        max_dimension: Max width/height.

    Returns:
        str: The actual path where the image was saved (with .jpg extension).
    """
    import cv2
    import numpy as np

    # Convert BGR to RGB for PIL
    rgb_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)

    return compress_and_save(pil_image, output_path, quality=quality, max_dimension=max_dimension)
