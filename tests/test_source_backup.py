# ==========================================
# 1. IMPORTS
# ==========================================

# Import hashlib to compute expected checksums
import hashlib

# Import os to check file permissions
import os

# Import shutil to simulate a failed copy
import shutil

# Import pytest to check raised errors
import pytest

# Import the backup functions
from ingestion.source_backup import (
    BackupIntegrityError,
    backup_source_file,
    load_manifest,
    prepare_working_copy,
    restore_backup,
    verify_backup,
)


# ==========================================
# 2. SAMPLE DATA HELPER
# ==========================================

def make_source(tmp_path, content=b"menu workbook bytes"):

    # Create a sample source file in its own raw folder
    source = tmp_path / "raw" / "menu.xlsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return source


# ==========================================
# 3. BACKUP CREATION TESTS
# ==========================================

def test_backup_is_exact_read_only_copy_with_metadata(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"

    record = backup_source_file(source, backup_dir)
    backup_path = backup_dir / record["backup_file"]

    # The backup holds the same bytes and is read-only
    assert backup_path.read_bytes() == source.read_bytes()
    assert not os.access(backup_path, os.W_OK)

    # The manifest records filename, checksum, size, and timestamp
    assert record["source_file"] == "menu.xlsx"
    assert record["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["size_bytes"] == source.stat().st_size
    assert record["backed_up_at"]
    assert load_manifest(backup_dir) == [record]


def test_same_file_twice_reuses_backup(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"

    first = backup_source_file(source, backup_dir)
    second = backup_source_file(source, backup_dir)

    # The original record is returned and no duplicate is added
    assert second == first
    assert len(load_manifest(backup_dir)) == 1


def test_changed_file_gets_new_backup_and_old_one_is_kept(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"
    first = backup_source_file(source, backup_dir)

    # A new version of the file arrives under the same name
    source.write_bytes(b"updated workbook bytes")
    second = backup_source_file(source, backup_dir)

    assert second["backup_file"] != first["backup_file"]
    assert verify_backup(first, backup_dir)
    assert verify_backup(second, backup_dir)
    assert len(load_manifest(backup_dir)) == 2


def test_source_is_not_modified(tmp_path):

    source = make_source(tmp_path)
    original_bytes = source.read_bytes()

    prepare_working_copy(source, tmp_path / "backups", tmp_path / "working")

    assert source.read_bytes() == original_bytes


def test_empty_source_is_rejected(tmp_path):

    source = make_source(tmp_path, content=b"")
    backup_dir = tmp_path / "backups"

    with pytest.raises(ValueError):
        backup_source_file(source, backup_dir)

    assert load_manifest(backup_dir) == []


# ==========================================
# 4. INTEGRITY AND FAILURE TESTS
# ==========================================

def test_corrupt_existing_backup_is_never_overwritten(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"
    record = backup_source_file(source, backup_dir)
    backup_path = backup_dir / record["backup_file"]

    # Simulate damage to the stored backup
    backup_path.chmod(0o666)
    backup_path.write_bytes(b"damaged")

    assert not verify_backup(record, backup_dir)
    with pytest.raises(BackupIntegrityError):
        backup_source_file(source, backup_dir)

    # The damaged file is left as evidence, not silently replaced
    assert backup_path.read_bytes() == b"damaged"


def test_failed_copy_leaves_no_backup(tmp_path, monkeypatch):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"

    # Simulate a copy that stops halfway
    def partial_copy(src, dst):
        with open(dst, "wb") as file:
            file.write(b"half")

    monkeypatch.setattr(shutil, "copyfile", partial_copy)

    with pytest.raises(BackupIntegrityError):
        backup_source_file(source, backup_dir)

    # Neither a backup, a partial file, nor a manifest record remains
    assert list(backup_dir.iterdir()) == []


# ==========================================
# 5. WORKING COPY AND RECOVERY TESTS
# ==========================================

def test_working_copy_is_separate_and_writable(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"

    working_file = prepare_working_copy(source, backup_dir, tmp_path / "working")

    assert working_file == tmp_path / "working" / "menu.xlsx"
    assert working_file.read_bytes() == source.read_bytes()

    # Editing the working copy does not affect the backup
    working_file.write_bytes(b"edited")
    assert verify_backup(load_manifest(backup_dir)[0], backup_dir)


def test_restore_recovers_lost_source(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"
    record = backup_source_file(source, backup_dir)
    original_bytes = source.read_bytes()

    # Simulate losing the source file, then recover it
    source.unlink()
    restore_backup(record, backup_dir, source)

    assert source.read_bytes() == original_bytes


def test_restore_refuses_corrupt_backup(tmp_path):

    source = make_source(tmp_path)
    backup_dir = tmp_path / "backups"
    record = backup_source_file(source, backup_dir)
    backup_path = backup_dir / record["backup_file"]
    backup_path.chmod(0o666)
    backup_path.write_bytes(b"damaged")

    destination = tmp_path / "recovered.xlsx"
    with pytest.raises(BackupIntegrityError):
        restore_backup(record, backup_dir, destination)

    assert not destination.exists()
