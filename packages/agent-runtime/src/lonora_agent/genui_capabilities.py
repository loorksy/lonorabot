"""The per-turn ``<lonora_ui_capabilities>`` block (GENUI_PLAN §3.6).

Only real capabilities: the intents whose tool path exists, the owner-wide delivery
channels that exist (today only in-app: no push channel exists, Q10; agent calls arrive in
phase 6, Q53/Q58), the client routes that exist and the owner's timezone and language.
The compiler checks every card against the same values.
"""

from dataclasses import dataclass

from lonora_contracts.genui_intents import S_A01_INTENTS

# Client routes that exist today (the web shell maps each to its page).
ROUTES = ("market", "tasks", "schedules", "usage", "chat-prefs", "files", "agents")
OPEN_KINDS = ("agent", "journal", "task", "operation", "watch", "message", "chart", "artifact")


@dataclass(frozen=True)
class UiCapabilities:
    intents: tuple[str, ...] = S_A01_INTENTS
    delivery: tuple[str, ...] = ("app",)
    routes: tuple[str, ...] = ROUTES
    timezone: str = "UTC"
    language: str = "ar"

    def block(self) -> str:
        return (
            "<lonora_ui_capabilities>\n"
            f"intents: {', '.join(self.intents)}\n"
            f"delivery: {', '.join(self.delivery)}\n"
            f"go: {', '.join(self.routes)}\n"
            f"timezone: {self.timezone} · language: {self.language}\n"
            "</lonora_ui_capabilities>"
        )


def capabilities(timezone: str | None = None, language: str = "ar") -> UiCapabilities:
    return UiCapabilities(timezone=timezone or "UTC", language=language)
