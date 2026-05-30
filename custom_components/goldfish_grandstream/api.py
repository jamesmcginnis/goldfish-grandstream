"""API client for Grandstream GXP phones."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

STATUS_MAP = {
    "available": "idle",
    "flash":     "idle",    # transient UI state seen on initial load
    "ringing":   "ringing",
    "calling":   "dialing",
    "oncall":    "in_call",
    "connected": "in_call",
    "busy":      "in_call",
    "holding":   "on_hold",
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
        """Log in to the phone and store the returned sid."""
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
                    raise GrandstreamAuthError(f"Login returned HTTP {resp.status}")
                body = await resp.json(content_type=None)
                _LOGGER.debug("Login response: %s", body)
                if body.get("response") != "success":
                    raise GrandstreamAuthError(f"Login failed: {body.get('response')}")
                self._sid = body["body"]["sid"]
                self._authenticated = True
                _LOGGER.debug("Authenticated, sid=%s", self._sid)
                return True
        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(f"Cannot connect to {self._host}: {err}") from err

    async def logout(self) -> None:
        """Log out so the browser session is not permanently occupied."""
        if not self._sid:
            return
        url = f"{self._base_url}/cgi-bin/dologout"
        try:
            async with self._session.post(
                url,
                data={"sid": self._sid},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                _LOGGER.debug("Logout response: %s", resp.status)
        except Exception:  # noqa: BLE001
            pass  # best-effort; don't raise on logout failure
        finally:
            self._authenticated = False
            self._sid = None

    async def get_phone_status(self, *, _retried: bool = False) -> dict[str, Any]:
        """Poll the phone's call status."""
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
                        raise GrandstreamConnectionError("401 after re-auth")
                    self._authenticated = False
                    await self.authenticate()
                    return await self.get_phone_status(_retried=True)
                body = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GrandstreamConnectionError(f"Cannot reach {self._host}: {err}") from err

        _LOGGER.debug("Phone status: %s", body)

        if body.get("response") != "success":
            if _retried:
                raise GrandstreamConnectionError(f"Status failed after re-auth: {body}")
            _LOGGER.debug("Non-success status response, re-authenticating: %s", body)
            self._authenticated = False
            await self.authenticate()
            return await self.get_phone_status(_retried=True)

        raw_status = body.get("body", "unknown")
        call_status = STATUS_MAP.get(raw_status)

        if call_status is None:
            _LOGGER.warning("Unmapped phone status %r — please report this", raw_status)
            call_status = raw_status

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
            raise GrandstreamConnectionError(f"Cannot reach {self._host}: {err}") from err

        _LOGGER.debug("Device info: %s", body)
        info = body.get("body", {})
        if not isinstance(info, dict):
            return {}
        return {
            "vendor": info.get("vendor_name", "Grandstream"),
            "model": info.get("phone_model", "GXP"),
            "firmware": info.get("68", "unknown"),
        }
