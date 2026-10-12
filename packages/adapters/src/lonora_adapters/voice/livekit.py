from livekit import api


class LiveKitTransport:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key, self.api_secret = api_key, api_secret

    async def join_token(self, room: str, identity: str) -> str:
        return (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(identity)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .to_jwt()
        )
