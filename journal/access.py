"""Per-installation bearer key, readable only by the owning OS account."""
import os
import secrets
import stat
from pathlib import Path


def access_key(data_dir):
    path = Path(data_dir) / "access.key"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as file:
            file.write(secrets.token_urlsafe(32))
            file.flush()
            os.fsync(file.fileno())

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd) as file:
        metadata = os.fstat(file.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("Erişim anahtarı normal bir dosya olmalı.")
        if os.name == "posix" and (metadata.st_uid != os.getuid() or metadata.st_mode & 0o077):
            raise RuntimeError("Erişim anahtarı yalnızca bu kullanıcı tarafından okunabilir olmalı (chmod 600).")
        value = file.read().strip()
    if len(value) < 32 or not value.isascii() or not all(c.isalnum() or c in "-_" for c in value):
        raise RuntimeError("Erişim anahtarı geçersiz.")
    return value
