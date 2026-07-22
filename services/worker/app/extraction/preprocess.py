"""OpenCV preprocessing for images headed into OCR: deskew, denoise,
contrast normalization, border removal, and downscaling. Best-effort at
every step — if any single step fails on a weird input, we fall back to
whatever we had rather than raising, since a slightly-worse OCR input is
far better than an aborted extraction.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MAX_LONGEST_SIDE_PX = 2000


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    arr = np.array(image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _cv_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


def _downscale(arr: np.ndarray) -> np.ndarray:
    h, w = arr.shape[:2]
    longest = max(h, w)
    if longest <= MAX_LONGEST_SIDE_PX:
        return arr
    scale = MAX_LONGEST_SIDE_PX / longest
    return cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _deskew(arr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return arr
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.5 or abs(angle) > 30:
        return arr  # not a real skew, or a detection artifact — leave it alone
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(arr, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _denoise(arr: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(arr, None, 5, 5, 7, 21)


def _normalize_contrast(arr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(arr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _remove_borders(arr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return arr
    x, y, w, h = cv2.boundingRect(coords)
    if w < 10 or h < 10:
        return arr
    pad = 5
    y0, x0 = max(0, y - pad), max(0, x - pad)
    y1, x1 = min(arr.shape[0], y + h + pad), min(arr.shape[1], x + w + pad)
    return arr[y0:y1, x0:x1]


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    try:
        arr = _pil_to_cv(image)
        arr = _downscale(arr)
        arr = _deskew(arr)
        arr = _denoise(arr)
        arr = _normalize_contrast(arr)
        arr = _remove_borders(arr)
        return _cv_to_pil(arr)
    except Exception:
        return image
