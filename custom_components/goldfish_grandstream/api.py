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
        self._sid: str | None = None
        self._base_url = f"http://{host}"

    async def authenticate(self) -> bool:
        """Log in to the phone via POST /cgi-bin/dologin.

        The phone performs a CSRF check on the Referer header, so it must
        be set to the phone's base URL. On success the phone returns a
        session ID (sid) in the JSON body which must be included in all
        subsequent requests.
        """
        url = f"{self._base_url}/cgi-bin/dologin"
        headers = {
            "Origin": self._base_url,
            "Referer": f"{self._base_url}/",
        }
        data = {
            "username": self._username,
            "password": self._password,
        }
        try:
            async with self._session.post(
                url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
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

                self._sid = body["body"]["sid"]
                self._authenticated = True
                _LOGGER.debug("Authenticated successfully, sid=%s", self._sid)
                return True

        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(
                f"Cannot connect to {self._host}: {err}"
            ) from err

    async def get_phone_status(self, *, _retried: bool = False) -> dict[str, Any]:
        """Poll the phone's call status.

        The sid obtained during authenticate() is sent in the POST body of
        every request — the phone uses token-based sessions, not cookies.

        Returns a dict with at minimum a 'call_status' key mapping to one of:
          'idle', 'ringing', 'in_call', or 'unknown'
        """
        if not self._authenticated:
            await self.authenticate()

        url = f"{self._base_url}/cgi-bin/api-get_phone_status"

        try:
            async with self._session.post(
                url,
                data={"sid": self._sid},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    # sid expired — re-auth and retry once
                    _LOGGER.debug("Session expired, re-authenticating")
                    self._authenticated = False
                    await self.authenticate()
                    async with self._session.post(
                        url,
                        data={"sid": self._sid},
                        timeout=aiohttp.ClientTimeout(total=10),
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
            # sid may have expired without a 401 — re-auth and retry once
            if _retried:
                raise GrandstreamConnectionError(
                    f"Phone status failed after re-authentication: {body}"
                )
            _LOGGER.warning(
                "Phone status returned non-success: %s — re-authenticating", body
            )
            self._authenticated = False
            await self.authenticate()
            return await self.get_phone_status(_retried=True)

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
        data = {
            "sid": self._sid,
            "request": "vendor_name:vendor_fullname:phone_model:68",
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

    async def refresh_session(self) -> None:
        """Call /cgi-bin/dorefresh to keep the sid alive between polls.

        The Grandstream browser UI calls this endpoint on every poll cycle.
        Without it the sid expires after a short idle period, causing the
        next get_phone_status call to fail with a non-success response.
        If the refresh fails (sid already expired) we simply re-authenticate.
        """
        if not self._authenticated or self._sid is None:
            await self.authenticate()
            return

        url = f"{self._base_url}/cgi-bin/dorefresh"
        try:
            async with self._session.post(
                url,
                data={"sid": self._sid, "tid": ""},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                body = await resp.json(content_type=None)
                _LOGGER.debug("dorefresh response: %s", body)

                if body.get("response") != "success":
                    # sid has expired — get a fresh one
                    _LOGGER.debug("sid expired during refresh, re-authenticating")
                    self._authenticated = False
                    await self.authenticate()
                else:
                    # dorefresh returns a new sid — update it
                    new_sid = body.get("body", {}).get("sid")
                    if new_sid:
                        self._sid = new_sid

        except aiohttp.ClientError as err:
            _LOGGER.warning("dorefresh failed, re-authenticating: %s", err)
            self._authenticated = False
            await self.authenticate()
