"""One Unix user per agent (7.1.1), stable across container re-creation.

The map from agent id to uid lives on the workspace disk itself (root only), beside the
files those uids own, so the two can never disagree: a restored database does not roll
the disk back, and a new disk starts with no owners. Accounts are rebuilt from the map
into /etc/passwd and /etc/group each time the container starts.
"""

import json
import os
import uuid
from pathlib import Path

FIRST_UID = 20000
LAST_UID = 59999
AGENTS_GID = 19999
AGENTS_GROUP = "agents"


def user_name(uid: int) -> str:
    return f"a{uid}"


def is_agent_uid(uid: int) -> bool:
    return FIRST_UID <= uid <= LAST_UID


class Users:
    def __init__(self, root: Path, etc: Path = Path("/etc")) -> None:
        self.root = root
        self.etc = etc
        self.state = root / ".lonora"
        self.path = self.state / "users.json"
        self.homes = root / "home"
        self.by_agent: dict[str, int] = {}

    def load(self) -> None:
        self.state.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.state, 0o700)
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self.by_agent = {str(uuid.UUID(k)): int(v) for k, v in raw.items()}
        if any(not is_agent_uid(uid) for uid in self.by_agent.values()) or len(
            set(self.by_agent.values())
        ) != len(self.by_agent):
            raise ValueError("workspace_users_corrupt")
        self.homes.mkdir(mode=0o755, exist_ok=True)
        self._write_accounts()

    def agent_of(self, uid: int) -> str | None:
        return next((agent for agent, value in self.by_agent.items() if value == uid), None)

    def home(self, uid: int) -> Path:
        return self.homes / user_name(uid)

    def ensure(self, agent_id: str) -> int:
        agent = str(uuid.UUID(agent_id))
        uid = self.by_agent.get(agent)
        if uid is None:
            used = set(self.by_agent.values())
            uid = next((n for n in range(FIRST_UID, LAST_UID + 1) if n not in used), None)
            if uid is None:
                raise ValueError("workspace_users_exhausted")
            self.by_agent[agent] = uid
            temporary = self.path.with_suffix(".next")
            temporary.write_text(json.dumps(self.by_agent, sort_keys=True))
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            self._write_accounts()
        home = self.home(uid)
        if not home.exists():
            # Created by root in a root-owned directory, then handed over: no path the
            # agent controls is ever followed by root.
            os.mkdir(home, 0o700)
            os.chown(home, uid, uid, follow_symlinks=False)
        return uid

    def _write_accounts(self) -> None:
        def keep(line: str, field: int) -> bool:
            parts = line.split(":")
            if len(parts) <= field or not parts[field].isdigit():
                return True
            number = int(parts[field])
            return not is_agent_uid(number) and number != AGENTS_GID

        passwd = [ln for ln in (self.etc / "passwd").read_text().splitlines() if keep(ln, 2)]
        group = [ln for ln in (self.etc / "group").read_text().splitlines() if keep(ln, 2)]
        uids = sorted(self.by_agent.values())
        passwd += [f"{user_name(u)}:x:{u}:{u}:Lonora agent:{self.home(u)}:/bin/bash" for u in uids]
        group += [f"{user_name(u)}:x:{u}:" for u in uids]
        group.append(f"{AGENTS_GROUP}:x:{AGENTS_GID}:{','.join(user_name(u) for u in uids)}")
        for name, lines in (("passwd", passwd), ("group", group)):
            target = self.etc / name
            temporary = self.etc / f".{name}.next"
            temporary.write_text("\n".join(lines) + "\n")
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
