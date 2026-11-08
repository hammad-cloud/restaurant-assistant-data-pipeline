# ==========================================
# 1. IMPORTS
# ==========================================

# Import hashlib to compute SHA-256 file checksums
import hashlib

# Import json to read and append backup manifest records
import json

# Import shutil to copy file contents
import shutil

# Import stat to mark backups read-only
import stat

# Import datetime to timestamp each backup in UTC
from datetime import datetime, timezone

# Import Path to manage folders and file paths
from pathlib import Path


# Name of the append-only metadata file inside the backup folder
MANIFEST_NAME = "manifest.jsonl"


class BackupIntegrityError(Exception):
    """A backup or copy does not match its expected SHA-256 checksum."""


# ==========================================
# 2. CHECKSUM
# ==========================================

def sha256_file(path):
    """
    Return the SHA-256 checksum of a file's exact bytes.
    """

    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


# ==========================================
# 3. VERIFIED COPY
# ==========================================

def _verified_copy(source, destination, expected_sha256):
    """
    Copy through a temporary file and rename it into place only
    when its checksum matches, so a failed copy never looks complete.
    """

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(destination.name + ".partial")

    try:
        # copyfile copies bytes only, so a read-only backup gives a writable copy
        shutil.copyfile(source, temp_path)

        if sha256_file(temp_path) != expected_sha256:
            raise BackupIntegrityError(f"Copy of {Path(source).name} is incomplete or corrupt.")

        temp_path.replace(destination)

    except Exception:
        # Remove the partial file and leave the destination untouched
        temp_path.unlink(missing_ok=True)
        raise

    return destination


# ==========================================
# 4. MANIFEST
# ==========================================

def load_manifest(backup_dir):
    """
    Return every backup record, oldest first (empty list if none).
    """

    manifest_path = Path(backup_dir) / MANIFEST_NAME
    if not manifest_path.exists():
        return []

    with open(manifest_path, encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


# ==========================================
# 5. CREATE BACKUP
# ==========================================

def backup_source_file(source, backup_dir):
    """
    Store an immutable, checksum-verified backup of a source file.

    The checksum is part of the backup name, so receiving the same file
    again reuses its backup, and a changed file gets a new backup
    instead of overwriting the old one.

    Returns the manifest record of the backup.
    """

    source = Path(source)
    backup_dir = Path(backup_dir)

    # An empty source is usually the result of a failed upload or copy
    size_bytes = source.stat().st_size
    if size_bytes == 0:
        raise ValueError(f"Source file {source.name} is empty; refusing to back it up.")

    source_sha256 = sha256_file(source)
    backup_path = backup_dir / f"{source.stem}_{source_sha256[:16]}{source.suffix}"

    if backup_path.exists():
        # Never replace an existing backup; a mismatch means it was damaged
        if sha256_file(backup_path) != source_sha256:
            raise BackupIntegrityError(f"Existing backup {backup_path.name} is corrupt.")
    else:
        # shortcut: exists-then-rename can race on POSIX (rename overwrites), fine for one pipeline run at a time
        _verified_copy(source, backup_path, source_sha256)

        # Mark the backup read-only so it is not edited by accident
        backup_path.chmod(stat.S_IREAD)

    # Reuse the original record when this exact file was already backed up
    for record in load_manifest(backup_dir):
        if record["backup_file"] == backup_path.name:
            return record

    record = {
        "source_file": source.name,
        "backup_file": backup_path.name,
        "sha256": source_sha256,
        "size_bytes": size_bytes,
        "backed_up_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # Append only: earlier records are never rewritten
    with open(backup_dir / MANIFEST_NAME, "a", encoding="utf-8") as file:
        file.write(json.dumps(record) + "\n")

    return record


# ==========================================
# 6. VERIFY AND RESTORE
# ==========================================

def verify_backup(record, backup_dir):
    """
    Return True when the backup exists and still matches its recorded checksum.
    """

    backup_path = Path(backup_dir) / record["backup_file"]
    return backup_path.exists() and sha256_file(backup_path) == record["sha256"]


def restore_backup(record, backup_dir, destination):
    """
    Copy a verified backup to destination (a working copy or a recovered
    source file) and confirm the copy matches the recorded checksum.
    """

    if not verify_backup(record, backup_dir):
        raise BackupIntegrityError(f"Backup {record['backup_file']} is missing or corrupt.")

    return _verified_copy(Path(backup_dir) / record["backup_file"], destination, record["sha256"])


def prepare_working_copy(source, backup_dir, working_dir):
    """
    Back up a source file, then create the working copy from the
    verified backup. ETL reads only the returned working copy.
    """

    record = backup_source_file(source, backup_dir)
    return restore_backup(record, backup_dir, Path(working_dir) / Path(source).name)
