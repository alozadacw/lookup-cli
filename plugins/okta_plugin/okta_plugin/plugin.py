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

**Devices.** `fetch_devices()` (surfaced as `okta <user> -d`) lists the
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
    OKTA_ACCESS_ATTRIBUTE       custom profile attribute carrying this org's
                                access decision (default `access_blocked`)
    LOOKUP_CLI_MOCK_OKTA=1      serve a fixture instead of calling out

**Custom profile attribute.** This org's Universal Directory defines an
attribute displayed in the Profile Editor as "ACCESS BLOCKED", variable
name `access_blocked`. It arrives inside the `profile` object of the user
payload we already fetch, so reading it costs no extra request. Its value
is reported verbatim -- a boolean stays `true`/`false` rather than becoming
yes/no -- so an operator sees exactly what the Okta admin UI shows. Only
the one configured attribute is read: Okta profiles routinely carry
manager, employee id and personal contact details, and everything in
`data` is written to the plaintext local cache.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
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

#: Custom Universal Directory attribute carrying this org's access decision.
#: Shown in the Okta Profile Editor as "ACCESS BLOCKED" with the variable
#: name `access_blocked`. Custom attribute names are org-specific, so the
#: name is overridable via OKTA_ACCESS_ATTRIBUTE rather than hardcoded.
DEFAULT_ACCESS_ATTRIBUTE = "access_blocked"

#: Label for that value in CLI output.
ACCESS_FIELD_LABEL = "access blocked"

#: Okta retains System Log data for roughly 90 days. Asking for longer cannot
#: return longer, and letting a caller believe otherwise would put a window in
#: the column header that the data does not actually cover.
MAX_LOG_WINDOW = timedelta(days=90)

#: Sign-in events that can carry device identity.
_SIGNIN_EVENT_TYPES = ("user.session.start", "user.authentication.sso")

_SINCE_RE = re.compile(r"^\s*(\d+)\s*([dh])\s*$", re.IGNORECASE)


def parse_since(raw: str) -> timedelta:
    """Parse a `--since` window like `90d` or `12h`, clamped to retention."""
    match = _SINCE_RE.match(raw or "")
    if not match:
        raise ValueError(
            f"could not parse --since {raw!r}. Use a number followed by "
            f"'d' (days) or 'h' (hours), e.g. 30d or 12h."
        )
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError("--since must be greater than zero.")
    window = timedelta(days=amount) if match.group(2).lower() == "d" else timedelta(hours=amount)
    return min(window, MAX_LOG_WINDOW)


def describe_window(window: timedelta) -> str:
    """Short label for a window, for the column header."""
    if window >= timedelta(days=1) and window.total_seconds() % 86400 == 0:
        return f"{int(window.total_seconds() // 86400)}d"
    return f"{int(window.total_seconds() // 3600)}h"

#: Okta's status enum has eight values, and the raw name is not always what
#: an operator needs to read. "Deactivated" in the Okta admin UI means
#: DEPROVISIONED specifically -- SUSPENDED also blocks login but is a
#: different state, and conflating them would mislead someone checking
#: whether an offboarding actually completed.
_DEACTIVATED_STATUS = "DEPROVISIONED"


def format_profile_value(raw: object) -> str:
    """Render a profile attribute exactly as Okta returned it.

    No interpretation: a boolean stays a boolean rather than becoming
    yes/no, so an operator sees the same value the Okta admin UI shows.
    `json.dumps` rather than `str` for non-strings, because Okta's JSON says
    `true` while Python's `str(True)` says `True`.

    An absent or null attribute has nothing to render verbatim, so it falls
    back to the table's usual empty marker -- which keeps it distinct from
    an explicit `false`.
    """
    if raw is None:
        return "-"
    if isinstance(raw, str):
        return raw
    return json.dumps(raw)


_STATUS_NOTES: dict[str, tuple[str, str]] = {
    "ACTIVE": ("green", ""),
    "DEPROVISIONED": ("red", "deactivated"),
    "SUSPENDED": ("red", "suspended"),
    "LOCKED_OUT": ("yellow", "locked out"),
    "PASSWORD_EXPIRED": ("yellow", "password expired"),
    "RECOVERY": ("yellow", "in password recovery"),
    "STAGED": ("yellow", "not yet activated"),
    "PROVISIONED": ("yellow", "activation pending"),
}


class OktaPlugin(ConnectorPlugin):
    name = "okta"
    required_credentials = ("OKTA_ORG_URL", "OKTA_API_TOKEN")

    @property
    def _access_attribute(self) -> str:
        return self.config.get("OKTA_ACCESS_ATTRIBUTE") or DEFAULT_ACCESS_ATTRIBUTE

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

        Pass `okta_id` when the caller already resolved the user (as the CLI
        does) to skip a redundant lookup. Like `fetch()`, this never raises
        for ordinary failures.
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

    async def fetch_device_signins(
        self,
        okta_id: str,
        *,
        since: timedelta,
        device_ids: set[str] | None = None,
    ) -> ConnectorResult:
        """Most recent successful sign-in per device, from the System Log.

        `/users/{id}/devices` has no last-login field -- its `lastUpdated`
        tracks changes to the device *record*, not sign-ins -- so this is a
        separate source correlated on `device.id`.

        Pass `device_ids` when the caller knows which devices it cares about:
        results come back newest-first, so once every device has been seen the
        remaining pages cannot change the answer and paging stops early. That
        matters because /api/v1/logs is Okta's most rate-limited endpoint.
        """
        try:
            signins = await self._call_logs_backend(okta_id, since, device_ids)
        except Exception as exc:  # noqa: BLE001 - contract: never crash aggregation
            return ConnectorResult(
                plugin_name=self.name,
                identifier=okta_id,
                error=safe_error(exc, secrets=[self.config.get("OKTA_API_TOKEN")]),
            )

        return ConnectorResult(
            plugin_name=self.name,
            identifier=okta_id,
            data={"signins": signins, "window": describe_window(since)},
        )

    # -- backend seam ---------------------------------------------------------

    async def _call_logs_backend(
        self, okta_id: str, since: timedelta, device_ids: set[str] | None
    ) -> dict[str, str]:
        if self.mock_mode:
            return self._mock_signins_fixture()

        org_url = self.config.require("OKTA_ORG_URL").rstrip("/")
        event_filter = " or ".join(f'eventType eq "{e}"' for e in _SIGNIN_EVENT_TYPES)
        params = {
            "since": (datetime.now(timezone.utc) - since).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "filter": f'actor.id eq "{okta_id}" and ({event_filter})',
            "sortOrder": "DESCENDING",
            "limit": "1000",
        }

        url = f"{org_url}/api/v1/logs"
        signins: dict[str, str] = {}
        seen_urls: set[str] = set()
        first = True

        async with self._client() as client:
            for _ in range(_MAX_PAGES):
                if url in seen_urls:
                    break
                seen_urls.add(url)

                response = await client.get(
                    url, headers=self._headers(), params=params if first else None
                )
                first = False
                if response.status_code in (401, 403):
                    raise RuntimeError(
                        "Okta refused the System Log request. This API token may lack "
                        "System Log read access, which is granted separately from user "
                        "read access."
                    )
                response.raise_for_status()

                for event in response.json():
                    if (event.get("outcome") or {}).get("result") != "SUCCESS":
                        continue
                    device_id = (event.get("device") or {}).get("id")
                    if not device_id:
                        # Not every auth event stamps a device. Guessing from
                        # the user agent could not tell two MacBooks apart, so
                        # an unattributable event is dropped rather than
                        # assigned to the wrong machine.
                        continue
                    # DESCENDING: the first sighting is the most recent.
                    signins.setdefault(device_id, event.get("published"))

                if device_ids and device_ids.issubset(signins):
                    break

                next_url = response.links.get("next", {}).get("url")
                if not next_url:
                    break
                url = next_url

        return signins

    def _mock_signins_fixture(self) -> dict[str, str]:
        return {"guoMOCK00000000000001": "2026-01-01T09:15:00.000Z"}


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
                # Fictional value; the real attribute's type is org-defined
                # and this connector does not care which it is.
                DEFAULT_ACCESS_ATTRIBUTE: False,
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
            "device_id": device.get("id") or entry.get("id"),
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
                # Verbatim: whatever Okta returned, uninterpreted. Placed
                # right after `status` so the CLI's ordered walk renders the
                # row directly beneath it.
                "access_blocked": profile.get(self._access_attribute),
                # Derived, but worth carrying: it is the single question
                # offboarding actually asks, and it keeps every consumer
                # (CLI, Stage 7 aggregation, JSON output) from re-deriving
                # which of eight enum values means "deactivated".
                "deactivated": status == _DEACTIVATED_STATUS,
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
        """`lookup-cli okta <identifier> [-s] [-d]`.

        Shape: `<service> <person> [what you want]`, with no noun
        subcommands. `okta status jdoe` and `okta devices jdoe` were removed
        on 2026-09-02 because they cannot coexist with `okta jdoe` -- a
        person whose Okta login is literally "status" or "devices" would
        silently resolve to the subcommand instead of being looked up.
        Stages 4-6 follow the same shape.

        Lives here, not in core `cli.py`, so this connector required no edit
        to `src/lookup_cli/`.
        """
        sub_app = typer.Typer(
            help="Okta account lookups.",
            # Required: Click groups stop parsing options once they hit a
            # positional, so without this `okta jdoe -d` fails while
            # `okta -d jdoe` works -- a confusing split for users.
            context_settings={"allow_interspersed_args": True},
        )
        console = Console()

        @sub_app.callback(invoke_without_command=True)
        def okta(
            identifier: str = typer.Argument(..., help="Okta username or email address."),
            status: bool = typer.Option(
                False,
                "--status",
                "-s",
                help="Show account status, including whether the user is deactivated. "
                "This is the default when no other flag is given.",
            ),
            devices: bool = typer.Option(
                False,
                "--devices",
                "-d",
                help="List devices registered to this user in Okta "
                "(Okta Verify / device trust -- not the Jamf or ABM inventory).",
            ),
            last_signin: bool = typer.Option(
                False,
                "--last-signin",
                help="Add each device's most recent sign-in, from the Okta System "
                "Log. Opt-in: it costs an extra call to a rate-limited endpoint. "
                "Implies --devices.",
            ),
            since: str = typer.Option(
                "90d",
                "--since",
                help="Window for --last-signin, e.g. 30d or 12h. Okta retains "
                "System Log data for about 90 days, which is the maximum.",
            ),
        ) -> None:
            """Look one person up in Okta."""
            # Asking for per-device sign-ins obviously means you want the
            # device table; requiring -d as well would just be pedantry.
            if last_signin:
                devices = True

            window = None
            if last_signin:
                try:
                    window = parse_since(since)
                except ValueError as exc:
                    console.print(f"[red]Invalid --since:[/red] {exc}")
                    raise typer.Exit(code=2)

            # Flags select sections. With none given, status is what people
            # want; `-d` alone means devices only.
            show_status = status or not devices

            result = asyncio.run(self.fetch(identifier))
            if not result.ok:
                console.print(f"[red]Okta lookup failed:[/red] {result.error}")
                raise typer.Exit(code=1)

            if not result.data.get("found"):
                console.print(f"[yellow]No Okta account found for[/yellow] {identifier}")
                return

            if show_status:
                _print_status(identifier, result)

            if devices:
                _print_devices(
                    identifier,
                    okta_id=result.properties.get("okta_id"),
                    window=window,
                    # With `-d` alone the devices ARE the answer, so a failure
                    # is a failed command. Alongside `-s` the status is already
                    # on screen, so it degrades that one section instead.
                    primary=not show_status,
                )

        def _print_status(identifier: str, result: ConnectorResult) -> None:
            status_value = result.data.get("status") or "UNKNOWN"
            colour, note = _STATUS_NOTES.get(status_value, ("yellow", ""))
            changed = (result.properties.get("status_changed") or "")[:10]

            suffix = ""
            if note:
                suffix = f" ({note}{' ' + changed if changed else ''})"
            console.print(
                f"[bold]{identifier}[/bold] - [{colour}]{status_value}[/{colour}]{suffix}"
            )

            table = Table(title=f"Okta - {identifier}")
            table.add_column("field")
            table.add_column("value")
            # `found` and `deactivated` are derived and already stated in the
            # line above; repeating them here is noise.
            for key, value in result.data.items():
                if key in ("found", "deactivated"):
                    continue
                if key == "access_blocked":
                    table.add_row(ACCESS_FIELD_LABEL, format_profile_value(value))
                else:
                    table.add_row(key, str(value) if value is not None else "-")
            for key, value in result.properties.items():
                table.add_row(key, str(value) if value is not None else "-")
            console.print(table)

        def _print_devices(
            identifier: str, okta_id: str | None, primary: bool, window: timedelta | None = None
        ) -> None:
            result = asyncio.run(self.fetch_devices(identifier, okta_id=okta_id))

            if not result.ok:
                console.print(f"[red]Devices unavailable:[/red] {result.error}")
                if primary:
                    raise typer.Exit(code=1)
                return

            if not result.data.get("found", True):
                console.print(f"[yellow]No Okta account found for[/yellow] {identifier}")
                return

            found = result.data["devices"]
            if not found:
                console.print(f"[yellow]No devices registered in Okta for[/yellow] {identifier}")
                return

            # Five columns, not seven: at a stock 80-column terminal rich
            # squeezes seven down until the serial renders as an empty cell.
            # Serial is the field an offboarding operator actually needs, so
            # it never wraps -- the name gives way instead.
            signins: dict[str, str] = {}
            signins_failed = False
            if window is not None:
                # Only the devices we are about to print, so paging can stop
                # as soon as they are all accounted for.
                wanted = {d["device_id"] for d in found if d.get("device_id")}
                signin_result = asyncio.run(
                    self.fetch_device_signins(
                        result.properties.get("okta_id") or okta_id or identifier,
                        since=window,
                        device_ids=wanted or None,
                    )
                )
                if signin_result.ok:
                    signins = signin_result.data["signins"]
                else:
                    # The inventory is a real answer on its own; losing sign-in
                    # times degrades one column rather than discarding it.
                    signins_failed = True
                    console.print(f"[yellow]Sign-in times unavailable:[/yellow] {signin_result.error}")

            table = Table(title=f"Devices ({result.data['count']}) - {identifier}")
            table.add_column("name")
            table.add_column("platform")
            # `model` gives way when the sign-in column is present. Six columns
            # re-create the 80-column squeeze that dropping from seven to five
            # fixed: model truncates to "MacBook..." and status wraps to three
            # lines. Of the two, model is the least actionable -- serial
            # identifies the machine and platform says what it is.
            if window is None:
                table.add_column("model")
            table.add_column("serial", no_wrap=True)
            table.add_column("status")
            if window is not None:
                # The window is in the header, not a footnote: a blank cell
                # means "not in this window", never "never used".
                table.add_column(f"last sign-in ({describe_window(window)})", no_wrap=True)
            for device in found:
                platform = " ".join(
                    part for part in (device["platform"], device["os_version"]) if part
                )
                state = " / ".join(
                    part for part in (device["status"], device["management_status"]) if part
                )
                row = [device["display_name"] or "-", platform or "-"]
                if window is None:
                    row.append(device["model"] or "-")
                row += [device["serial_number"] or "-", state or "-"]
                if window is not None:
                    if signins_failed:
                        row.append("?")
                    else:
                        stamp = signins.get(device.get("device_id") or "")
                        row.append(stamp[:10] if stamp else "-")
                table.add_row(*row)
            console.print(table)

        return sub_app
