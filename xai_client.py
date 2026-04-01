"""
xAI Grok Imagine API client for image-to-video generation.

Flow:
  1. Read image file, encode as base64 data URI
  2. POST to /v1/videos/generations with image + prompt
  3. Get back a request_id
  4. Poll GET /v1/videos/{request_id} until status is "done"
  5. Download the video from the temporary URL
"""

import base64
import io
import time
import logging
import mimetypes
from pathlib import Path

import requests
from PIL import Image

import config

logger = logging.getLogger(__name__)


class XAIClient:
    """Client for xAI Grok Imagine video generation API."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.XAI_API_KEY
        if not self.api_key:
            raise ValueError("XAI_API_KEY not set. Add it to your .env file.")
        self.base_url = config.XAI_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _image_to_data_uri(self, image_path: Path) -> str:
        """Read an image file and return a base64 data URI."""
        image_path = Path(image_path)
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type:
            mime_type = "image/jpeg"

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        return f"data:{mime_type};base64,{b64}"

    def _stitch_references(self, image_paths: list[Path], max_height: int = 1024) -> str:
        """
        Stitch multiple reference images side-by-side into one composite.
        Returns a base64 data URI of the composite JPEG.
        """
        images = [Image.open(p) for p in image_paths]

        # Resize all to the same height, preserving aspect ratio
        resized = []
        for img in images:
            ratio = max_height / img.height
            new_w = int(img.width * ratio)
            resized.append(img.resize((new_w, max_height), Image.LANCZOS))

        total_width = sum(img.width for img in resized)
        composite = Image.new("RGB", (total_width, max_height))

        x = 0
        for img in resized:
            composite.paste(img, (x, 0))
            x += img.width

        buf = io.BytesIO()
        composite.save(buf, format="JPEG", quality=90)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        for img in images:
            img.close()

        return f"data:image/jpeg;base64,{b64}"

    def edit_image(self, image_paths: list[Path], prompt: str, save_path: Path) -> dict:
        """
        Edit image(s) using xAI Aurora image editing.
        Accepts a list of reference image paths — stitches them into a single
        composite so the model sees front + left + right angles.
        Returns the path to the saved edited image and its URL.
        """
        image_paths = [Path(p) for p in image_paths]
        if len(image_paths) == 1:
            data_uri = self._image_to_data_uri(image_paths[0])
        else:
            data_uri = self._stitch_references(image_paths)

        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model": "grok-imagine-image",
            "prompt": prompt,
            "image": {"url": data_uri},
            "aspect_ratio": "2:3",
        }

        resp = self.session.post(
            f"{self.base_url}/images/edits",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        image_url = data["data"][0]["url"]

        img_resp = self.session.get(image_url, timeout=60)
        img_resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(img_resp.content)

        logger.info(f"  Edited image saved: {save_path.name}")
        return {"path": save_path, "image_url": image_url}

    def generate_video(self, image_path: Path, prompt: str,
                       duration: int = None, aspect_ratio: str = None,
                       resolution: str = None) -> str:
        """
        Submit an image-to-video generation request.
        Returns the request_id for polling.
        """
        data_uri = self._image_to_data_uri(image_path)

        payload = {
            "model": config.VIDEO_MODEL,
            "prompt": prompt,
            "image": {"url": data_uri},
        }

        payload["duration"]     = duration     or config.VIDEO_DURATION
        payload["aspect_ratio"] = aspect_ratio or config.VIDEO_ASPECT_RATIO
        payload["resolution"]   = resolution   or config.VIDEO_RESOLUTION

        logger.info(f"Submitting video generation: {Path(image_path).name}")

        resp = self.session.post(
            f"{self.base_url}/videos/generations",
            json=payload,
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(
                f"Video submit failed ({resp.status_code}): {resp.text}"
            )
        data = resp.json()

        request_id = data["request_id"]
        return request_id

    def poll_video(self, request_id: str, poll_interval: int = None,
                   timeout: int = None) -> dict:
        """
        Poll until the video is ready.
        Returns the full response dict with status and video URL.
        """
        poll_interval = poll_interval or config.POLL_INTERVAL
        timeout = timeout or config.POLL_TIMEOUT
        start = time.time()

        while time.time() - start < timeout:
            resp = self.session.get(
                f"{self.base_url}/videos/{request_id}",
                timeout=30,
            )
            if not resp.ok:
                raise RuntimeError(
                    f"Video poll failed ({resp.status_code}) for {request_id}: {resp.text}"
                )
            data = resp.json()

            status = data.get("status", "unknown")

            if status == "done":
                duration = data.get("video", {}).get("duration", "?")
                logger.info(f"  Video ready! Duration: {duration}s")
                return data

            elif status in ("expired", "failed"):
                raise RuntimeError(f"Video generation {status}: {data}")

            time.sleep(poll_interval)

        raise TimeoutError(f"Video not ready after {timeout}s (request: {request_id})")

    def download_video(self, video_url: str, save_path: Path) -> Path:
        """Download the generated video from the temporary URL."""
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading video to {save_path}...")
        resp = self.session.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = save_path.stat().st_size / (1024 * 1024)
        logger.info(f"Saved: {save_path} ({size_mb:.1f} MB)")
        return save_path

    def process_photo(self, image_path: Path, prompt: str,
                      save_name: str = None) -> dict:
        """
        Full pipeline for a single photo: submit -> poll -> download.

        Returns a dict with:
            "path"      - Path to the locally saved video file
            "video_url" - The original (temporary) xAI CDN URL
                          Use this immediately for Instagram before it expires.
        """
        image_path = Path(image_path)
        save_name = save_name or image_path.stem
        save_path = config.VIDEOS_DIR / f"{save_name}.mp4"

        # Submit
        request_id = self.generate_video(image_path, prompt)

        # Poll
        result = self.poll_video(request_id)
        video_url = result["video"]["url"]

        # Download locally for archive
        local_path = self.download_video(video_url, save_path)

        return {"path": local_path, "video_url": video_url}
