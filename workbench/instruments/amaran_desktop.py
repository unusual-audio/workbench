from __future__ import annotations

import json
from base64 import b64decode, b64encode
from os import getenv, urandom
from random import randint
from time import time, sleep
from typing import Any

import dotenv
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from websocket import WebSocket

from workbench.instruments import Instrument


class AmaranFixture:

    def __init__(self, amaran_desktop: AmaranDesktop, name: str, node_id: str):
        self.amaran_desktop = amaran_desktop
        self.name = name
        self.node_id = node_id

    def get_sleep(self) -> bool:
        return self.amaran_desktop.request("get_sleep", node_id=self.node_id)

    def set_sleep(self, sleep: bool):
        self.amaran_desktop.request("set_sleep", node_id=self.node_id, args={"sleep": bool(sleep)})

    def get_intensity(self) -> int:
        return self.amaran_desktop.request("get_intensity", node_id=self.node_id)

    def set_intensity(self, intensity: int):
        intensity = int(max(0, min(intensity, 1000)))
        self.amaran_desktop.request("set_intensity", node_id=self.node_id, args={"intensity": intensity})

    def __repr__(self):
        return f"<AmaranFixture {self.name!r}>"


class AmaranDesktop(Instrument):
    instrument_name = "Amaran Desktop"

    def __init__(self, uri: str, secret_key: str):
        self.uri = uri
        self.secret_key = secret_key

    def get_fixture(self, name: str) -> AmaranFixture:
        for i in self.request("get_fixture_list"):
            if i["name"] == name:
                return AmaranFixture(self, name, i["node_id"])
        raise ValueError(f"Fixture {name!r} not found")

    def get_fixtures(self):
        return [AmaranFixture(self, i["name"], i["node_id"]) for i in self.request("get_fixture_list")]

    def request(self, action: str, **kwargs: Any) -> Any:
        request_id = randint(0, 32000)
        ws = WebSocket()
        ws.connect(self.uri)  # See <https://tools.sidus.link/openapi/docs/protocol>
        try:
            request_message = {
                "version": 2,
                "type": "request",
                "client_id": 1,
                "request_id": request_id,
                "action": action,
                "token": self.get_token(self.secret_key),
            }
            request_message.update(kwargs or {})

            ws.send(json.dumps(request_message))
            responses = json.loads(ws.recv())
            if responses["code"] != 0:
                raise Exception(f"Error {responses['code']}: {responses['message']}")
            return responses["data"]
        finally:
            ws.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @classmethod
    def connect(cls, uri: str = "ws://127.0.0.1:12345/") -> AmaranDesktop:
        dotenv.load_dotenv()
        secret_key = getenv("AMARAN_API_KEY")
        return cls(uri, secret_key)

    @staticmethod
    def get_token(secret_key):
        iv = urandom(12)
        encryptor = Cipher(algorithms.AES(b64decode(secret_key)), modes.GCM(iv)).encryptor()
        ciphertext = encryptor.update(str(int(time())).encode()) + encryptor.finalize()
        combined = iv + encryptor.tag + ciphertext
        return b64encode(combined).decode()
