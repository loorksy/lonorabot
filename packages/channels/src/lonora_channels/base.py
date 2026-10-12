from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelManifest:
    id: str
    inbound: bool
    outbound: bool
