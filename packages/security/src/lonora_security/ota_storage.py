"""Read immutable OTA files without following any repository-controlled symlink."""

import os
import stat
from pathlib import Path

from lonora_core.user_error import LonoraError


def read_ota_file(root: Path, components: tuple[str, ...], limit: int) -> bytes:
    descriptors: list[int] = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for component in components[:-1]:
            if component in {"", ".", ".."} or "/" in component:
                raise LonoraError("mobile_update_invalid", 503)
            directory = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            descriptors.append(directory)
        descriptor = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        descriptors.append(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise LonoraError("mobile_update_invalid", 503)
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            result = stream.read(limit + 1)
        if len(result) > limit:
            raise LonoraError("mobile_update_invalid", 503)
        return result
    except FileNotFoundError:
        raise LonoraError("mobile_update_not_found", 404) from None
    except OSError:
        raise LonoraError("mobile_update_invalid", 503) from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
