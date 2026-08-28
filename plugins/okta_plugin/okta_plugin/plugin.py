"""
Okta connector: account status for one person.

Endpoint: `GET {OKTA_ORG_URL}/api/v1/users/{login}` with an
`Authorization: SSWS <token>` header.

**Not-found semantics.** A user Okta has never heard of returns a
*successful* result with `data["found"] is False`, not `error=`. The guide
asks each connector to decide this explicitly: for an offboarding lookup,
"this person has no Okta account" is a real answer, whereas an `error=`
would make `UnifiedUserRecord.field_for("okta")` return None and be
indistinguishable from "Okta was unreachable".

**Devices.** `fetch_devices()` (surfaced as `okta status -d`) lists the
devices Okta associates with a user, via
`GET /api/v1/users/{userId}/devices`. Scope caveat worth repeating to
users: this is Okta's own device registry -- machines enrolled through
Okta Verify / device trust -- and NOT the Jamf or ABM hardware inventory
that Stages 4-5 will add. Someone can hold a laptop that Okta has never
seen. It is deliberately a separate call, not part of `fetch()`, because
Stage 7 runs `fetch()` for every plugin on every lookup and shouldn't pay
for a second round trip nobody asked for.

Required env vars (see `.env.example`):
    OKTA_ORG_URL        e.g. https://acme.okta.com
    OKTA_API_TOKEN      an SSWS token
Optional:
    OKTA_TIMEOUT_SECONDS        per-request timeout (default 10)
    LOOKUP_CLI_MOCK_OKTA=1      serve a fixture instead of calling out
"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import httpx
import typer
from rich.console import Console
from rich.table import Table

from lookup_cli.plugins.base import ConnectorPlugin, ConnectorResult
from lookup_cli.redaction import safe_error

DEFAULT_TIMEOUT_SECONDS = 10.0

#: Okta statuses that mean the account can actually be used.
_ACTIVE_STATUSES = frozenset({"ACTIVE"})

#: Hard bound on Link-header following, so a looping or malformed `next`
#: can't hang the CLI. Far above any real user's device count.
_MAX_PAGES = 20


class OktaPlugin(ConnectorPlugin):
    name = "okta"
    required_credentials = ("OKTA_ORG_URL", "OKTA_API_TOKEN")

    async def fetch(self, identifier: str) -> ConnectorResult:
        try:
            raw = await self._call_backend(identifier)
        except Exception as exc:  # noqa: BLE001 - contract: never crash aggregation
            return ConnectorResult(
                plugin_name=self.name,
                identifier=identifier,
                # The token is passed explicitly as well as being picked up
                # from the environment: in mock/test runs it may only exist
                # in the injected config.
                error=safe_error(exc, secrets=[self.config.get("OKTA_API_TOKEN")]),
            )

        if raw is None:
            return ConnectorResult(
                plugin_name=self.name,
                identifier=identifier,
                data={"found": False, "status": None},
                tags=["not-found"],
            )

        return self._to_result(identifier, raw)

    async def fetch_devices(self, identifier: str, *, okta_id: str | None = None) -> ConnectorResult:
        """List the devices Okta associates with `identifier`.

        Pass `okta_id` when the caller already resolved the user (as
        `status -d` does) to skip a redundant lookup. Like `fetch()`, this
        never raises for ordinary failures.
        """
        try:
            if okta_id is None:
                user = await self._call_backend(identifier)
                if user is None:
                    return ConnectorResult(
                        plugin_name=self.name,
                        identifier=identifier,
                        data={"found": False, "devices": [], "count": 0},
                        tags=["not-found"],
                    )
                okta_id = user.get("id")

            raw_devices = await self._call_devices_backend(okta_id)
        except Exception as exc:  # noqa: BLE001 - contract: never crash aggregation
            return ConnectorResult(
                plugin_name=self.name,
                identifier=identifier,
                error=safe_error(exc, secrets=[self.config.get("OKTA_API_TOKEN")]),
            )

        devices = [self._to_device(entry) for entry in raw_devices]
        return ConnectorResult(
            plugin_name=self.name,
            identifier=identifier,
            data={"found": True, "devices": devices, "count": len(devices)},
            properties={"okta_id": okta_id},
            tags=["no-devices"] if not devices else ["has-devices"],
        )

    # -- backend seam ---------------------------------------------------------

    async def _call_devices_backend(self, okta_id: str) -> list[dict]:
        if self.mock_mode:
            return self._mock_devices_fixture()

        org_url = self.config.require("OKTA_ORG_URL").rstrip("/")
        url = f"{org_url}/api/v1/users/{quote(okta_id, safe='')}/devices"

        entries: list[dict] = []
        seen_urls: set[str] = set()

        async with self._client() as client:
            for _ in range(_MAX_PAGES):
                if url in seen_urls:
                    break  # self-referential `next`; stop rather than loop
                seen_urls.add(url)

                response = await client.get(url, headers=self._headers())
                if response.status_code == 404:
                    # The user exists (we just resolved them), so a 404 here
                    # means the device API itself is unavailable -- typically
                    # an Okta Classic org. Say that, don't say "not found".
                    raise RuntimeError(
                        "Okta returned 404 for the device endpoint. This org may not "
                        "have Okta Identity Engine device management enabled, or the "
                        "API token may lack the devices scope."
                    )
                response.raise_for_status()

                page = response.json()
                entries.extend(page)

                next_url = response.links.get("next", {}).get("url")
                if not next_url:
                    break
                url = next_url

        return entries

    async def _call_backend(self, identifier: str) -> dict | None:
        """Return the raw Okta user payload, or None if there's no such user."""
        if self.mock_mode:
            return self._mock_fixture(identifier)

        org_url = self.config.require("OKTA_ORG_URL").rstrip("/")

        # `identifier` is user input. quote(safe="") keeps an email's `@`
        # working while stopping `../` from walking off /api/v1/users.
        url = f"{org_url}/api/v1/users/{quote(identifier, safe='')}"

        async with self._client() as client:
            response = await client.get(url, headers=self._headers())

        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def _client(self) -> httpx.AsyncClient:
        """A timeout-bounded client, so one slow call can't hang a lookup."""
        timeout = float(self.config.get("OKTA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
        return httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"SSWS {self.config.require('OKTA_API_TOKEN')}",
            "Accept": "application/json",
        }

    def _mock_fixture(self, identifier: str) -> dict:
        return {
            "id": "00uMOCK0000000000000",
            "status": "ACTIVE",
            "created": "2024-01-01T00:00:00.000Z",
            "activated": "2024-01-01T00:05:00.000Z",
            "statusChanged": "2024-01-01T00:05:00.000Z",
            "lastLogin": "2026-01-01T00:00:00.000Z",
            "profile": {
                "firstName": "Mock",
                "lastName": "User",
                "email": f"{identifier}@example.com",
                "login": identifier,
            },
        }

    def _mock_devices_fixture(self) -> list[dict]:
        return [
            {
                "id": "guoMOCK00000000000001",
                "managementStatus": "MANAGED",
                "device": {
                    "id": "guoMOCK00000000000001",
                    "status": "ACTIVE",
                    "lastUpdated": "2026-01-01T00:00:00.000Z",
                    "profile": {
                        "displayName": "Mock MacBook Pro",
                        "platform": "MACOS",
                        "manufacturer": "Apple",
                        "model": "MacBookPro18,3",
                        "osVersion": "15.6.0",
                        "serialNumber": "C02MOCK00001",
                    },
                },
            }
        ]

    # -- shaping --------------------------------------------------------------

    @staticmethod
    def _to_device(entry: dict) -> dict:
        """Normalise one device entry.

        Okta returns a link object wrapping a `device`; tolerate a flat
        device object too, since not every response nests it.
        """
        device = entry.get("device") or entry
        profile = device.get("profile") or {}
        return {
            "display_name": profile.get("displayName"),
            "platform": profile.get("platform"),
            "manufacturer": profile.get("manufacturer"),
            "model": profile.get("model"),
            "os_version": profile.get("osVersion"),
            "serial_number": profile.get("serialNumber"),
            "status": device.get("status"),
            "management_status": entry.get("managementStatus"),
            "last_updated": device.get("lastUpdated"),
        }


    def _to_result(self, identifier: str, raw: dict) -> ConnectorResult:
        profile = raw.get("profile") or {}
        status = raw.get("status")
        names = [profile.get("firstName"), profile.get("lastName")]
        display_name = " ".join(part for part in names if part) or None

        return ConnectorResult(
            plugin_name=self.name,
            identifier=identifier,
            data={
                "found": True,
                "status": status,
                "login": profile.get("login"),
                "email": profile.get("email"),
                "display_name": display_name,
            },
            # Optional detail goes here rather than growing `data`'s schema.
            properties={
                "okta_id": raw.get("id"),
                "created": raw.get("created"),
                "activated": raw.get("activated"),
                "status_changed": raw.get("statusChanged"),
                "last_login": raw.get("lastLogin"),
            },
            tags=["active" if status in _ACTIVE_STATUSES else "inactive"],
        )

    # -- CLI ------------------------------------------------------------------

    def cli(self) -> typer.Typer:
        """`lookup-cli okta status <identifier>`.

        Lives here, not in core `cli.py`, so adding this connector required
        no edit to `src/lookup_cli/`.
        """
        sub_app = typer.Typer(help="Okta account lookups.")
        console = Console()

        @sub_app.command("status")
        def status(
            identifier: str,
            devices: bool = typer.Option(
                False,
                "--devices",
                "-d",
                help=(
                    "Also list devices registered to this user in Okta "
                    "(Okta Verify / device trust -- not the Jamf or ABM inventory)."
                ),
            ),
        ) -> None:
            """Show one person's Okta account status."""
            result = asyncio.run(self.fetch(identifier))

            if not result.ok:
                console.print(f"[red]Okta lookup failed:[/red] {result.error}")
                raise typer.Exit(code=1)

            if not result.data.get("found"):
                console.print(f"[yellow]No Okta account found for[/yellow] {identifier}")
                return

            table = Table(title=f"Okta - {identifier}")
            table.add_column("field")
            table.add_column("value")
            for key, value in result.data.items():
                if key != "found":
                    table.add_row(key, str(value) if value is not None else "-")
            for key, value in result.properties.items():
                table.add_row(key, str(value) if value is not None else "-")
            console.print(table)

            if devices:
                # Reuse the id we already resolved rather than looking the
                # user up a second time.
                _print_devices(identifier, okta_id=result.properties.get("okta_id"))

        def _print_devices(identifier: str, okta_id: str | None) -> None:
            result = asyncio.run(self.fetch_devices(identifier, okta_id=okta_id))

            if not result.ok:
                # The account status above is the primary answer; a device-API
                # problem degrades that one section rather than failing the
                # whole command.
                console.print(f"[red]Devices unavailable:[/red] {result.error}")
                return

            found = result.data["devices"]
            if not found:
                console.print(f"[yellow]No devices registered in Okta for[/yellow] {identifier}")
                return

            # Five columns, not seven: at a stock 80-column terminal rich
            # squeezes seven down until the serial renders as an empty cell.
            # Serial is the field an offboarding operator actually needs, so
            # it never wraps -- the name gives way instead.
            table = Table(title=f"Devices ({result.data['count']}) - {identifier}")
            table.add_column("name")
            table.add_column("platform")
            table.add_column("model")
            table.add_column("serial", no_wrap=True)
            table.add_column("status")
            for device in found:
                platform = " ".join(
                    part for part in (device["platform"], device["os_version"]) if part
                )
                state = " / ".join(
                    part for part in (device["status"], device["management_status"]) if part
                )
                table.add_row(
                    device["display_name"] or "-",
                    platform or "-",
                    device["model"] or "-",
                    device["serial_number"] or "-",
                    state or "-",
                )
            console.print(table)

        return sub_app
