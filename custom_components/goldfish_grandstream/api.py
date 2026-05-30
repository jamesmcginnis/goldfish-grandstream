"""API client for Grandstream GXP phones."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# All known call status values returned by the phone in body field
STATUS_MAP = {
    "available": "idle",
    "ringing": "ringing",       # incoming call
    "calling": "dialing",       # outbound call in progress
    "oncall": "in_call",        # active call (both directions)
    "connected": "in_call",     # some firmware versions use this
    "holding": "on_hold",
    "busy": "busy",
    "unavailable": "unavailable",
    "offline": "unavailable",
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

    async def refresh_session(self) -> None:
        """Call /cgi-bin/dorefresh to keep the sid alive between polls.

        The Grandstream browser UI calls this on every poll cycle. If the
        refresh fails (e.g. phone is busy during a call) we keep the
        existing sid and carry on — the phone will reject it if it really
        has expired, and get_phone_status will handle re-auth at that point.
        """
        if not self._authenticated or self._sid is None:
            await self.authenticate()
            return

        url = f"{self._base_url}/cgi-bin/dorefresh"
        try:
            async with self._session.post(
                url,
                data={"sid": self._sid, "tid": ""},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                body = await resp.json(content_type=None)
                _LOGGER.debug("dorefresh response: %s", body)

                if body.get("response") == "success":
                    # Phone returns a refreshed sid — keep it up to date
                    new_sid = body.get("body", {}).get("sid")
                    if new_sid:
                        self._sid = new_sid
                else:
                    # sid expired — re-authenticate
                    _LOGGER.debug("sid expired, re-authenticating")
                    self._authenticated = False
                    await self.authenticate()

        except (aiohttp.ClientError, Exception) as err:
            # Phone may be too busy during a call to respond to dorefresh.
            # Keep the existing sid and let get_phone_status deal with it.
            _LOGGER.debug("dorefresh failed (phone may be busy): %s", err)

    async def get_phone_status(self, *, _retried: bool = False) -> dict[str, Any]:
        """Poll the phone's call status.

        The sid obtained during authenticate() is sent in the POST body of
        every request — the phone uses token-based sessions, not cookies.

        Returns a dict with at minimum a 'call_status' key.
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
                    if _retried:
                        raise GrandstreamConnectionError(
                            "Phone status failed with 401 after re-authentication"
                        )
                    _LOGGER.debug("401 received, re-authenticating")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.get_phone_status(_retried=True)

                body = await resp.json(content_type=None)

        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(
                f"Cannot reach {self._host}: {err}"
            ) from err

        _LOGGER.debug("Phone status response: %s", body)

        if body.get("response") != "success":
            if _retried:
                raise GrandstreamConnectionError(
                    f"Phone status failed after re-authentication: {body}"
                )
            _LOGGER.debug(
                "Phone status non-success: %s — re-authenticating", body
            )
            self._authenticated = False
            await self.authenticate()
            return await self.get_phone_status(_retried=True)

        raw_status = body.get("body", "unknown")
        call_status = STATUS_MAP.get(raw_status, raw_status)

        # Log unmapped statuses so we can add them to STATUS_MAP later
        if raw_status not in STATUS_MAP:
            _LOGGER.warning(
                "Unknown phone status %r — please report this so it can be added",
                raw_status,
            )

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
