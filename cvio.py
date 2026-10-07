"""Unicode-safe cv2.imread / cv2.imwrite.

OpenCV on Windows cannot open paths with non-ASCII characters (e.g. "새 폴더").
Importing this module replaces cv2.imread/imwrite with numpy-based versions.
"""
import os

import cv2
import numpy as np

_imread, _imwrite = cv2.imread, cv2.imwrite


def imread(path, flags=cv2.IMREAD_COLOR):
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite(path, img, params=None):
    ext = os.path.splitext(str(path))[1] or ".png"
    ok, buf = cv2.imencode(ext, img, params if params is not None else [])
    if not ok:
        return False
    buf.tofile(str(path))
    return True


if not getattr(cv2, "_unicode_io", False):
    cv2.imread, cv2.imwrite, cv2._unicode_io = imread, imwrite, True
