"""Local, review-required image OCR using the Windows built-in recognizer.

No image or recognized text is sent to a network service. The PowerShell bridge
must be present at scripts/windows_ocr.ps1 in the project checkout.
"""

import hashlib
import json
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Dict


_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif"}
_TIMEOUT_SECONDS = 90
_WARNING = (
    "Windows.Media.Ocr does not provide confidence scores. OCR text and any "
    "derived fields require manual review; no extracted field is verified."
)


class OCRError(RuntimeError):
    """The local OCR engine could not safely extract the image."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_image_text(image_path: Path, language: str = "ko") -> dict:
    """Extract one image without changing it; results always need human review.

    Accepted formats are PNG, JPEG, BMP, TIFF and GIF, subject to installed
    Windows codecs. Multi-frame images are rejected rather than silently losing
    pages. Images exceeding OcrEngine.MaxImageDimension are rejected: split into
    overlapping smaller images or resize a copy before retrying.

    Raises OCRError for unsupported platforms, invalid inputs, missing languages,
    decoder failures, oversized images, bridge errors, or the 90-second timeout.
    Bounding boxes use image pixels, with the origin at the top-left.
    """
    if platform.system() != "Windows":
        raise OCRError("Local image OCR requires Windows 10/11 and Windows.Media.Ocr.")
    if not isinstance(language, str) or not re.fullmatch(
        r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language
    ):
        raise OCRError("OCR language must be a language tag such as 'ko' or 'en-US'.")
    try:
        source = Path(image_path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise OCRError("OCR source must be an existing image file, not a directory.")
        if source.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            raise OCRError(
                "Unsupported image extension. Use PNG, JPEG, BMP, TIFF or GIF."
            )
        source_hash = _sha256(source)
    except (OSError, TypeError, ValueError) as exc:
        raise OCRError("Cannot read OCR image path: {}".format(exc)) from exc

    bridge = Path(__file__).resolve().parents[2] / "scripts" / "windows_ocr.ps1"
    powershell = (
        Path(os.environ.get("SystemRoot", "C:/Windows"))
        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    if not bridge.is_file():
        raise OCRError("Windows OCR bridge is missing: {}".format(bridge))
    if not powershell.is_file():
        raise OCRError("Windows PowerShell executable is missing: {}".format(powershell))

    # Send paths as JSON data, never interpolated into PowerShell source code.
    try:
        completed = subprocess.run(
            [
                str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(bridge),
            ],
            input=json.dumps({"image_path": str(source), "language": language}, ensure_ascii=False),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="strict",
            timeout=_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OCRError("Windows image OCR timed out after 90 seconds; try a smaller image copy.") from exc
    except (OSError, UnicodeError) as exc:
        raise OCRError("Cannot run Windows OCR bridge: {}".format(exc)) from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "No error details."
        try:
            error = json.loads(message).get("error", {})
            message = "{}: {}".format(error["code"], error["message"])
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
        raise OCRError("Windows image OCR failed: {}".format(message))
    try:
        payload: Dict[str, Any] = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        if payload.get("engine") != "Windows.Media.Ocr":
            raise ValueError("Unexpected OCR engine.")
        if not isinstance(payload.get("language"), str):
            raise ValueError("Missing recognized language.")
        for name in ("width", "height"):
            if type(payload.get(name)) is not int or payload[name] <= 0:
                raise ValueError("Invalid image {}.".format(name))
        if not isinstance(payload.get("text"), str) or not isinstance(payload.get("lines"), list):
            raise ValueError("Missing recognized text or line list.")
    except (ValueError, TypeError) as exc:
        raise OCRError("Invalid UTF-8 JSON response from Windows OCR: {}".format(exc)) from exc

    try:
        if _sha256(source) != source_hash:
            raise OCRError("OCR source changed during extraction; retry with a stable image copy.")
    except OSError as exc:
        raise OCRError("Cannot recheck OCR source after extraction: {}".format(exc)) from exc
    payload.update(
        source_path=str(source),
        source_sha256=source_hash,
        requested_language=language,
        requires_review=True,
        warning=_WARNING,
    )
    return payload
