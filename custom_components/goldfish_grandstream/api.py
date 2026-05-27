"""API client for Grandstream GXP phones."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Known call status values from pcap analysis
CALL_STATUS_AVAILABLE = "available"
CALL_STATUS_RINGING = "ringing"
CALL_STATUS_ONCALL = "oncall"

STATUS_MAP = {
    CALL_STATUS_AVAILABLE: "idle",
    CALL_STATUS_RINGING: "ringing",
    CALL_STATUS_ONCALL: "in_call",
}


class GrandstreamAuthError(Exception):
    """Raised when authentication fails."""


class GrandstreamConnectionError(Exception):
    """Raised when connection to the phone fails."""


class GrandstreamApiClient:
    """Handles communication with the Grandstream GXP HTTP API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._sid: str | None = None
        self._base_url = f"http://{host}"

    def _hash_password(self, password: str) -> str:
        """Hash password with MD5 as required by Grandstream API."""
        return hashlib.md5(password.encode()).hexdigest()  # noqa: S324

    async def authenticate(self) -> bool:
        """Log in to the phone and retrieve a session token (sid).

        The Grandstream web UI sends a two-step login:
          1. POST /cgi-bin/api-login with username + hashed password
          2. Response contains a sid token used for all subsequent requests
        """
        url = f"{self._base_url}/cgi-bin/api-login"
        hashed_pw = self._hash_password(self._password)
        data = {
            "username": self._username,
            "password": hashed_pw,
        }
        try:
            async with self._session.post(
                url, data=data, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    raise GrandstreamAuthError(
                        f"Login returned HTTP {resp.status}"
                    )
                body = await resp.json(content_type=None)
                _LOGGER.debug("Login response: %s", body)

                if body.get("response") != "success":
                    raise GrandstreamAuthError(
                        f"Login failed: {body.get('response')}"
                    )

                sid = body.get("body", {})
                if isinstance(sid, dict):
                    sid = sid.get("sid")
                if not sid or sid == "flash":
                    # Some firmware versions return sid differently
                    # Try fetching it via api.values.get
                    sid = await self._fetch_sid()

                self._sid = sid
                _LOGGER.debug("Authenticated, sid=%s", self._sid)
                return True

        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(
                f"Cannot connect to {self._host}: {err}"
            ) from err

    async def _fetch_sid(self) -> str:
        """Fetch the session ID via the api.values.get endpoint.

        Some GXP firmware versions return the sid via this endpoint
        rather than inline in the login response body.
        """
        url = f"{self._base_url}/cgi-bin/api.values.get"
        data = {"request": "sid"}
        async with self._session.post(
            url, data=data, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            body = await resp.json(content_type=None)
            _LOGGER.debug("sid fetch response: %s", body)
            sid = body.get("body", {})
            if isinstance(sid, dict):
                return sid.get("sid", "")
            return str(sid)

    async def get_phone_status(self) -> dict[str, Any]:
        """Poll the phone's call status.

        Returns a dict with at minimum a 'call_status' key mapping to one of:
          'idle', 'ringing', 'in_call', or 'unknown'
        """
        if not self._sid:
            await self.authenticate()

        url = f"{self._base_url}/cgi-bin/api-get_phone_status"
        data = {"sid": self._sid}

        try:
            async with self._session.post(
                url, data=data, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 401:
                    # Session expired — re-auth and retry once
                    _LOGGER.debug("Session expired, re-authenticating")
                    await self.authenticate()
                    data["sid"] = self._sid
                    async with self._session.post(
                        url, data=data, timeout=aiohttp.ClientTimeout(total=10)
                    ) as retry_resp:
                        body = await retry_resp.json(content_type=None)
                else:
                    body = await resp.json(content_type=None)

        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(
                f"Cannot reach {self._host}: {err}"
            ) from err

        _LOGGER.debug("Phone status response: %s", body)

        if body.get("response") != "success":
            # Sid may have expired without a 401
            _LOGGER.warning(
                "Phone status returned non-success: %s — re-authenticating", body
            )
            await self.authenticate()
            return await self.get_phone_status()

        raw_status = body.get("body", "unknown")
        call_status = STATUS_MAP.get(raw_status, "unknown")

        return {
            "call_status": call_status,
            "raw_status": raw_status,
            "misc": body.get("misc", "0"),
        }

    async def get_device_info(self) -> dict[str, Any]:
        """Fetch device information (model, firmware, etc.)."""
        if not self._sid:
            await self.authenticate()

        url = f"{self._base_url}/cgi-bin/api.values.get"
        # Parameters observed in pcap: vendor_name, phone_model, firmware (key 68)
        data = {
            "request": "vendor_name:vendor_fullname:phone_model:68",
            "sid": self._sid,
        }

        try:
            async with self._session.post(
                url, data=data, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                body = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(
                f"Cannot reach {self._host}: {err}"
            ) from err

        _LOGGER.debug("Device info response: %s", body)
        info = body.get("body", {})
        if not isinstance(info, dict):
            return {}

        return {
            "vendor": info.get("vendor_name", "Grandstream"),
            "model": info.get("phone_model", "GXP"),
            "firmware": info.get("68", "unknown"),
        }
