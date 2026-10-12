"""Post journal lines to Microsoft Dynamics 365 Business Central (API v2.0).

Authentication is OAuth 2.0 client credentials against Microsoft Entra ID: a
registered app with the Business Central "API.ReadWrite.All" application
permission, added in Business Central as a Microsoft Entra application with only
the permission sets it needs. No user password is involved.

Posting is idempotent: before adding lines, the client looks for lines that
already carry the day's document number and refuses to post the day twice.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .journal import JournalLine

LOGIN = "https://login.microsoftonline.com"
BC_API = "https://api.businesscentral.dynamics.com/v2.0"
SCOPE = "https://api.businesscentral.dynamics.com/.default"


@dataclass(frozen=True)
class BCConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    environment: str  # e.g. "Production" or "Sandbox"
    company_id: str
    journal_name: str  # the general journal batch, e.g. "POS"


class BusinessCentralError(RuntimeError):
    pass


class BusinessCentral:
    def __init__(self, config: BCConfig, http: httpx.Client | None = None):
        self.config = config
        self.http = http or httpx.Client(timeout=30)
        self._token: str | None = None
        self._token_expires = 0.0

    # ------------------------------------------------------------- auth

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        r = self.http.post(
            f"{LOGIN}/{self.config.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": SCOPE,
            },
        )
        if r.status_code != 200:
            raise BusinessCentralError(f"Token request failed: {r.status_code} {r.text}")
        body = r.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        for attempt in range(4):
            r = self.http.request(
                method, url, headers={"Authorization": f"Bearer {self._access_token()}"}, **kwargs
            )
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(int(r.headers.get("Retry-After", 2**attempt)))
                continue
            if r.status_code >= 400:
                raise BusinessCentralError(f"{method} {url}: {r.status_code} {r.text}")
            return r
        raise BusinessCentralError(f"{method} {url}: gave up after retries ({r.status_code})")

    # ------------------------------------------------------------- journals

    @property
    def _company(self) -> str:
        c = self.config
        return f"{BC_API}/{c.tenant_id}/{c.environment}/api/v2.0/companies({c.company_id})"

    def journal_id(self) -> str:
        name = self.config.journal_name.replace("'", "''")
        r = self._request("GET", f"{self._company}/journals", params={"$filter": f"code eq '{name}'"})
        found = r.json()["value"]
        if not found:
            raise BusinessCentralError(f"No general journal batch named {self.config.journal_name}")
        return found[0]["id"]

    def existing_lines(self, journal_id: str, document_no: str) -> list[dict]:
        doc = document_no.replace("'", "''")
        r = self._request(
            "GET",
            f"{self._company}/journals({journal_id})/journalLines",
            params={"$filter": f"documentNumber eq '{doc}'"},
        )
        return r.json()["value"]

    def add_lines(self, lines: list[JournalLine], post: bool = False) -> int:
        """Add the day's lines to the journal batch. With post=True, also post the batch."""
        if not lines:
            return 0
        documents = {l.document_no for l in lines}
        if len(documents) != 1:
            raise ValueError("Add one document (one business day) at a time")
        document_no = documents.pop()
        journal_id = self.journal_id()
        if self.existing_lines(journal_id, document_no):
            raise BusinessCentralError(f"{document_no} is already in the journal; not adding it twice")

        for line in lines:
            self._request(
                "POST",
                f"{self._company}/journals({journal_id})/journalLines",
                json={
                    "accountType": "G/L Account",
                    "accountNumber": line.account,
                    "postingDate": line.posting_date.isoformat(),
                    "documentNumber": line.document_no,
                    "description": line.description[:100],
                    "amount": float(line.amount),  # API expects a JSON number; values are already cents
                },
            )
        if post:
            self._request("POST", f"{self._company}/journals({journal_id})/Microsoft.NAV.post")
        return len(lines)
