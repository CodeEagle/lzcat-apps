FROM python:3.11-slim

ARG UPSTREAM_REPO=BIT-DataLab/Edit-Banana
ARG UPSTREAM_REF=0ed16c8
ARG SAM3_REPO=facebookresearch/sam3
ARG SAM3_REF=f6e51f59500a87c576c2df2323ce56b9fd7a12de

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OUTPUT_DIR=/app/output \
    EDIT_BANANA_UPSTREAM_REPO=${UPSTREAM_REPO} \
    EDIT_BANANA_SOURCE_REF=${UPSTREAM_REF} \
    EDIT_BANANA_SAM3_REPO=${SAM3_REPO} \
    EDIT_BANANA_SAM3_REF=${SAM3_REF}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN curl -fsSL "https://codeload.github.com/${UPSTREAM_REPO}/tar.gz/${UPSTREAM_REF}" \
    | tar -xz --strip-components=1 -C /app \
    && mkdir -p /tmp/sam3 \
    && curl -fsSL "https://codeload.github.com/${SAM3_REPO}/tar.gz/${SAM3_REF}" \
    | tar -xz --strip-components=1 -C /tmp/sam3 \
    && python - <<'PY'
from pathlib import Path

path = Path("/app/modules/text/ocr/__init__.py")
path.write_text(
    '''"""
OCR sources.

Includes:
    - LocalOCR: local Tesseract OCR
    - Pix2TextOCR: optional Pix2Text formula OCR
    - TextBlock, OCRResult: shared data structures
"""

from .base import TextBlock, OCRResult
from .local_ocr import LocalOCR

try:
    from .pix2text import Pix2TextOCR, Pix2TextBlock, Pix2TextResult
except Exception:
    Pix2TextOCR = None
    Pix2TextBlock = None
    Pix2TextResult = None

__all__ = [
    "TextBlock",
    "OCRResult",
    "LocalOCR",
    "Pix2TextOCR",
    "Pix2TextBlock",
    "Pix2TextResult",
]
''',
    encoding="utf-8",
)

model_builder = Path("/tmp/sam3/sam3/model_builder.py")
model_builder.write_text(
    model_builder.read_text(encoding="utf-8").replace(
        """from sam3.model.sam1_task_predictor import SAM3InteractiveImagePredictor
from sam3.model.sam3_image import Sam3Image, Sam3ImageOnVideoMultiGPU
from sam3.model.sam3_tracking_predictor import Sam3TrackerPredictor
from sam3.model.sam3_video_inference import Sam3VideoInferenceWithInstanceInteractivity
from sam3.model.sam3_video_predictor import Sam3VideoPredictorMultiGPU
""",
        """try:
    from sam3.model.sam1_task_predictor import SAM3InteractiveImagePredictor
except ModuleNotFoundError:
    SAM3InteractiveImagePredictor = None

try:
    from sam3.model.sam3_image import Sam3Image, Sam3ImageOnVideoMultiGPU
    from sam3.model.sam3_tracking_predictor import Sam3TrackerPredictor
    from sam3.model.sam3_video_inference import Sam3VideoInferenceWithInstanceInteractivity
    from sam3.model.sam3_video_predictor import Sam3VideoPredictorMultiGPU
except ModuleNotFoundError:
    from sam3.model.sam3_image import Sam3Image

    Sam3ImageOnVideoMultiGPU = None
    Sam3TrackerPredictor = None
    Sam3VideoInferenceWithInstanceInteractivity = None
    Sam3VideoPredictorMultiGPU = None
""",
    ),
    encoding="utf-8",
)

sam3_image = Path("/tmp/sam3/sam3/model/sam3_image.py")
sam3_image_text = sam3_image.read_text(encoding="utf-8")
sam3_image_text = sam3_image_text.replace(
    "from typing import Dict, List, Optional, Tuple\n",
    "from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING\n",
)
sam3_image_text = sam3_image_text.replace(
    "from sam3.model.sam1_task_predictor import SAM3InteractiveImagePredictor\n",
    """try:
    from sam3.model.sam1_task_predictor import SAM3InteractiveImagePredictor
except ModuleNotFoundError:
    SAM3InteractiveImagePredictor = None
""",
)
sam3_image_text = sam3_image_text.replace(
    "from sam3.train.data.collator import BatchedDatapoint\n",
    """if TYPE_CHECKING:
    from sam3.train.data.collator import BatchedDatapoint
else:
    BatchedDatapoint = Any
""",
)
sam3_image.write_text(sam3_image_text, encoding="utf-8")

position_encoding = Path("/tmp/sam3/sam3/model/position_encoding.py")
position_encoding.write_text(
    position_encoding.read_text(encoding="utf-8").replace(
        '                tensors = torch.zeros((1, 1) + size, device="cuda")\n',
        '                tensors = torch.zeros((1, 1) + size, device="cuda" if torch.cuda.is_available() else "cpu")\n',
    ),
    encoding="utf-8",
)

decoder = Path("/tmp/sam3/sam3/model/decoder.py")
decoder.write_text(
    decoder.read_text(encoding="utf-8").replace(
        '                coords_h, coords_w = self._get_coords(\n                    feat_size, feat_size, device="cuda"\n                )\n',
        '                coords_h, coords_w = self._get_coords(\n                    feat_size,\n                    feat_size,\n                    device="cuda" if torch.cuda.is_available() else "cpu",\n                )\n',
    ),
    encoding="utf-8",
)

app_sam3 = Path("/app/modules/sam3_info_extractor.py")
app_sam3.write_text(
    app_sam3.read_text(encoding="utf-8").replace(
        "        self._processor = Sam3Processor(self._model)\n",
        "        self._processor = Sam3Processor(self._model, device=self.device)\n",
    ),
    encoding="utf-8",
)

geometry_encoders = Path("/tmp/sam3/sam3/model/geometry_encoders.py")
geometry_encoders.write_text(
    geometry_encoders.read_text(encoding="utf-8").replace(
        "            scale = scale.pin_memory().to(device=boxes_xyxy.device, non_blocking=True)\n",
        "            if boxes_xyxy.device.type == \"cuda\":\n                scale = scale.pin_memory().to(device=boxes_xyxy.device, non_blocking=True)\n            else:\n                scale = scale.to(device=boxes_xyxy.device)\n",
    ),
    encoding="utf-8",
)
PY

COPY docker/entrypoint.sh /usr/local/bin/lazycat-entrypoint
COPY docker/server_pa.py /app/server_pa.py

RUN chmod +x /usr/local/bin/lazycat-entrypoint \
    && python -m pip install --upgrade pip wheel "setuptools<81" \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && python -m pip install /tmp/sam3 \
    && python -m pip install \
        "numpy>=1.26,<2" \
        "opencv-python-headless<4.11" \
        "timm>=1.0.17" \
        tqdm \
        "ftfy==6.1.1" \
        regex \
        "iopath>=0.1.10" \
        huggingface_hub \
        einops \
        -r requirements.txt \
        python-multipart \
    && python - <<'PY'
import pkg_resources
import sam3.model_builder

print("pkg_resources and sam3.model_builder are importable")
PY

EXPOSE 8000

CMD ["lazycat-entrypoint"]
