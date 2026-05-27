"""API client for Grandstream GXP phones."""
from __future__ import annotations

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
        self._authenticated = False
        self._base_url = f"http://{host}"

    async def authenticate(self) -> bool:
        """Log in to the phone via POST /cgi-bin/dologin.

        The GXP sends username and password as plain text form fields.
        On success the phone sets a session cookie (HttpOnly + session-role)
        which aiohttp's cookie jar retains automatically for all subsequent
        requests on this session.
        """
        url = f"{self._base_url}/cgi-bin/dologin"
        data = {
            "username": self._username,
            "password": self._password,
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

                self._authenticated = True
                _LOGGER.debug("Authenticated successfully with cookie session")
                return True

        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(
                f"Cannot connect to {self._host}: {err}"
            ) from err

    async def get_phone_status(self) -> dict[str, Any]:
        """Poll the phone's call status.

        The session cookie set during authenticate() is sent automatically
        by aiohttp's cookie jar — no sid needed in the POST body.

        Returns a dict with at minimum a 'call_status' key mapping to one of:
          'idle', 'ringing', 'in_call', or 'unknown'
        """
        if not self._authenticated:
            await self.authenticate()

        url = f"{self._base_url}/cgi-bin/api-get_phone_status"

        try:
            async with self._session.post(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 401:
                    # Session cookie expired — re-auth and retry once
                    _LOGGER.debug("Session expired, re-authenticating")
                    await self.authenticate()
                    async with self._session.post(
                        url, timeout=aiohttp.ClientTimeout(total=10)
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
            # Cookie may have expired without a 401 — re-auth and retry once
            _LOGGER.warning(
                "Phone status returned non-success: %s — re-authenticating", body
            )
            self._authenticated = False
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
        if not self._authenticated:
            await self.authenticate()

        url = f"{self._base_url}/cgi-bin/api.values.get"
        # Parameters observed in pcap: vendor_name, phone_model, firmware (key 68)
        data = {"request": "vendor_name:vendor_fullname:phone_model:68"}

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
