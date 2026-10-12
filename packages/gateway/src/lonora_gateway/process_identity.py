import socket
from uuid import uuid4


def process_identity() -> str:
    return socket.gethostname() + "-" + str(uuid4())
