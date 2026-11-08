"""A scripted standards-shaped authenticator for disposable test owners only.

Private signing material stays in this test process. Production always verifies
with the WebAuthn library; no test-only authorization switch exists.
"""

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Any

import cbor2
from check_streaming import Fixture
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from lonora_auth.devices import relying_party
from webauthn.helpers import bytes_to_base64url


@dataclass
class Device:
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1()), repr=False
    )
    identifier: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    count: int = 0

    def client_data(self, challenge: dict[str, Any], origin: str, kind: str) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": challenge["publicKey"]["challenge"],
                "origin": origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode()

    def cose_key(self) -> bytes:
        point = self.key.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: point.x.to_bytes(32, "big"), -3: point.y.to_bytes(32, "big")}
        )

    def registration(self, challenge: dict[str, Any], origin: str) -> dict[str, Any]:
        auth_data = (
            hashlib.sha256(relying_party(origin).encode()).digest()
            + bytes([0x45])
            + bytes(4)
            + bytes(16)
            + len(self.identifier).to_bytes(2, "big")
            + self.identifier
            + self.cose_key()
        )
        return {
            "challenge_id": challenge["challenge_id"],
            "credential": {
                "id": bytes_to_base64url(self.identifier),
                "rawId": bytes_to_base64url(self.identifier),
                "type": "public-key",
                "response": {
                    "clientDataJSON": bytes_to_base64url(
                        self.client_data(challenge, origin, "webauthn.create")
                    ),
                    "attestationObject": bytes_to_base64url(
                        cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
                    ),
                    "transports": ["internal"],
                },
            },
        }

    def assertion(
        self, challenge: dict[str, Any], origin: str, *, verified: bool = True
    ) -> dict[str, Any]:
        self.count += 1
        client_data = self.client_data(challenge, origin, "webauthn.get")
        data = (
            hashlib.sha256(relying_party(origin).encode()).digest()
            + bytes([0x05 if verified else 0x01])
            + self.count.to_bytes(4, "big")
        )
        signed = self.key.sign(
            data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "challenge_id": challenge["challenge_id"],
            "credential": {
                "id": bytes_to_base64url(self.identifier),
                "rawId": bytes_to_base64url(self.identifier),
                "type": "public-key",
                "response": {
                    "clientDataJSON": bytes_to_base64url(client_data),
                    "authenticatorData": bytes_to_base64url(data),
                    "signature": bytes_to_base64url(signed),
                },
            },
        }

    @classmethod
    async def enroll(cls, fixture: Fixture) -> "Device":
        device = cls()
        challenge = await fixture.request(
            "POST",
            "/auth/devices/enrollment",
            {
                "password": os.environ.get("LONORA_UI_TEST_PASSWORD", "ci-only-owner-password"),
                "name": "Scripted test authenticator",
            },
        )
        await fixture.request(
            "POST",
            "/auth/devices/enrollment/verify",
            device.registration(challenge, fixture.settings.allowed_origin),
        )
        return device

    async def sign_grant(self, fixture: Fixture, proposal: dict[str, Any]) -> dict[str, Any]:
        """Sign a pending grant through the owner routes, as the trading-level controls do."""
        challenge = await fixture.request(
            "POST", f"/account-authorities/{proposal['id']}/challenge", {}
        )
        return await fixture.request(
            "POST",
            "/account-authorities/verify",
            self.assertion(challenge, fixture.settings.allowed_origin),
        )
