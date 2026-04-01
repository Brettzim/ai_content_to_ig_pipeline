"""
Instagram Graph API client for posting Reels.

Flow per video:
  1. Create a media container  (POST /{ig_user_id}/media)
  2. Poll until status_code == FINISHED
  3. Publish                   (POST /{ig_user_id}/media_publish)

The video must be at a publicly accessible URL. We pass the xAI temporary
URL directly — it's still hot right after generation, so no re-hosting needed.
"""

import time
import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

CONTAINER_POLL_INTERVAL = 20   # seconds between status checks
CONTAINER_POLL_TIMEOUT  = 300  # max seconds to wait for IG to process


@dataclass
class IGAccount:
    name: str
    ig_user_id: str


class InstagramClient:
    """Posts Reels to a single Instagram Business account via the Graph API."""

    def __init__(self, account: IGAccount, access_token: str):
        self.account = account
        self.access_token = access_token
        self.session = requests.Session()

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _post(self, path: str, payload: dict) -> dict:
        payload = {**payload, "access_token": self.access_token}
        url = f"{GRAPH_API_BASE}/{path}"
        resp = self.session.post(url, json=payload, timeout=60)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            logger.error(f"API error {resp.status_code}: {detail}")
            raise requests.HTTPError(f"{resp.status_code}: {detail}", response=resp)
        return resp.json()

    def _get(self, path: str, params: dict = None) -> dict:
        params = {**(params or {}), "access_token": self.access_token}
        url = f"{GRAPH_API_BASE}/{path}"
        resp = self.session.get(url, params=params, timeout=30)
        try:
            resp.raise_for_status()
        except requests.HTTPError:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            logger.error(f"API error {resp.status_code}: {detail}")
            raise requests.HTTPError(f"{resp.status_code}: {detail}", response=resp)
        return resp.json()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def create_reel_container(self, video_url: str, caption: str = "") -> str:
        """
        Submit the video URL to Instagram. Returns the container (creation) ID.
        The video_url must be publicly accessible — use the xAI temp URL while fresh.
        """
        logger.info(f"[{self.account.name}] Creating Reel container...")
        data = self._post(
            f"{self.account.ig_user_id}/media",
            {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "share_to_feed": "true",
            },
        )
        container_id = data["id"]
        logger.info(f"[{self.account.name}] Container ID: {container_id}")
        return container_id

    def poll_container(self, container_id: str) -> None:
        """Block until Instagram finishes processing the container."""
        start = time.time()
        while time.time() - start < CONTAINER_POLL_TIMEOUT:
            data = self._get(container_id, {"fields": "status_code,status"})
            status = data.get("status_code", "UNKNOWN")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError(
                    f"[{self.account.name}] Instagram container error: {data.get('status')}"
                )
            time.sleep(CONTAINER_POLL_INTERVAL)

        raise TimeoutError(
            f"[{self.account.name}] Container {container_id} not ready after "
            f"{CONTAINER_POLL_TIMEOUT}s"
        )

    def publish_container(self, container_id: str) -> str:
        """Publish the finished container. Returns the live media ID."""
        data = self._post(
            f"{self.account.ig_user_id}/media_publish",
            {"creation_id": container_id},
        )
        return data["id"]

    def post_photo(self, image_url: str, caption: str = "") -> str:
        """
        Post a photo to Instagram. Returns the live media ID.
        """
        logger.info(f"[{self.account.name}] Creating photo container...")
        data = self._post(
            f"{self.account.ig_user_id}/media",
            {
                "image_url": image_url,
                "caption": caption,
            },
        )
        container_id = data["id"]
        logger.info(f"[{self.account.name}] Container ID: {container_id}")
        self.poll_container(container_id)
        return self.publish_container(container_id)

    def post_reel(self, video_url: str, caption: str = "") -> str:
        """
        Full pipeline for one Reel: create → poll → publish.
        Returns the live Instagram media ID.
        """
        container_id = self.create_reel_container(video_url, caption)
        self.poll_container(container_id)
        return self.publish_container(container_id)
