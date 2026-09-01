import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

DATA_DIR = (
    PROJECT_ROOT
    / "data"
)

DATABASE_FILE = (
    DATA_DIR
    / "medical_scribe.db"
)

RECORDINGS_DIR = (
    PROJECT_ROOT
    / "recordings"
)

AUDIT_DIR = (
    DATA_DIR
    / "audit"
)

BACKUP_ROOT = (
    PROJECT_ROOT
    / "backups"
)


def calculate_sha256(
    file_path: Path
):

    sha256 = hashlib.sha256()

    with file_path.open(
        "rb"
    ) as file:

        for chunk in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):

            sha256.update(
                chunk
            )

    return sha256.hexdigest()


def copy_file_with_hash(
    source: Path,
    destination: Path,
):

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )

    return {
        "path": str(
            destination.relative_to(
                destination.parents[1]
            )
        ),
        "sha256": calculate_sha256(
            destination
        ),
        "size_bytes": (
            destination.stat().st_size
        ),
    }


def create_backup():

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    backup_dir = (
        BACKUP_ROOT
        / timestamp
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    manifest = {
        "backup_id": timestamp,
        "created_at": (
            datetime.now().isoformat()
        ),
        "files": [],
    }

    if DATABASE_FILE.exists():

        destination = (
            backup_dir
            / "data"
            / DATABASE_FILE.name
        )

        manifest["files"].append(
            copy_file_with_hash(
                DATABASE_FILE,
                destination,
            )
        )

    if RECORDINGS_DIR.exists():

        for source in RECORDINGS_DIR.rglob(
            "*"
        ):

            if not source.is_file():
                continue

            relative_path = (
                source.relative_to(
                    RECORDINGS_DIR
                )
            )

            destination = (
                backup_dir
                / "recordings"
                / relative_path
            )

            manifest["files"].append(
                copy_file_with_hash(
                    source,
                    destination,
                )
            )

    if AUDIT_DIR.exists():

        for source in AUDIT_DIR.rglob(
            "*"
        ):

            if not source.is_file():
                continue

            relative_path = (
                source.relative_to(
                    AUDIT_DIR
                )
            )

            destination = (
                backup_dir
                / "audit"
                / relative_path
            )

            manifest["files"].append(
                copy_file_with_hash(
                    source,
                    destination,
                )
            )

    manifest_path = (
        backup_dir
        / "manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "success": True,
        "backup_id": timestamp,
        "backup_path": str(
            backup_dir
        ),
        "file_count": len(
            manifest["files"]
        ),
    }


def verify_backup(
    backup_id: str
):

    backup_dir = (
        BACKUP_ROOT
        / backup_id
    )

    manifest_path = (
        backup_dir
        / "manifest.json"
    )

    if not manifest_path.exists():

        return {
            "valid": False,
            "error": (
                "Backup manifest not found."
            ),
        }

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    failed_files = []

    for file_info in manifest.get(
        "files",
        [],
    ):

        relative_path = file_info.get(
            "path"
        )

        expected_hash = file_info.get(
            "sha256"
        )

        file_path = (
            backup_dir
            / relative_path
        )

        if not file_path.exists():

            failed_files.append(
                relative_path
            )
            continue

        actual_hash = (
            calculate_sha256(
                file_path
            )
        )

        if actual_hash != expected_hash:

            failed_files.append(
                relative_path
            )

    return {
        "valid": (
            len(
                failed_files
            )
            == 0
        ),
        "failed_files": (
            failed_files
        ),
    }


def list_backups():

    BACKUP_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    backups = []

    for backup_dir in sorted(
        BACKUP_ROOT.iterdir(),
        reverse=True,
    ):

        if not backup_dir.is_dir():
            continue

        manifest_path = (
            backup_dir
            / "manifest.json"
        )

        if not manifest_path.exists():
            continue

        try:

            manifest = json.loads(
                manifest_path.read_text(
                    encoding="utf-8"
                )
            )

            backups.append(
                {
                    "backup_id": (
                        manifest.get(
                            "backup_id"
                        )
                    ),
                    "created_at": (
                        manifest.get(
                            "created_at"
                        )
                    ),
                    "file_count": len(
                        manifest.get(
                            "files",
                            [],
                        )
                    ),
                }
            )

        except Exception:

            continue

    return backups


def restore_backup(
    backup_id: str
):

    backup_dir = (
        BACKUP_ROOT
        / backup_id
    )

    if not backup_dir.exists():

        return {
            "success": False,
            "error": "Backup not found.",
        }


    verification = verify_backup(
        backup_id
    )

    if not verification.get(
        "valid"
    ):

        return {
            "success": False,
            "error": (
                "Backup verification failed."
            ),
            "failed_files": (
                verification.get(
                    "failed_files",
                    [],
                )
            ),
        }


    # --------------------------------------------------------
    # SAFETY BACKUP BEFORE RESTORE
    # --------------------------------------------------------

    safety_backup = create_backup()


    # --------------------------------------------------------
    # RESTORE DATABASE
    # --------------------------------------------------------

    backup_database = (
        backup_dir
        / "data"
        / "medical_scribe.db"
    )

    if backup_database.exists():

        DATABASE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            backup_database,
            DATABASE_FILE,
        )


    # --------------------------------------------------------
    # RESTORE RECORDINGS
    # --------------------------------------------------------

    backup_recordings = (
        backup_dir
        / "recordings"
    )

    if backup_recordings.exists():

        if RECORDINGS_DIR.exists():

            shutil.rmtree(
                RECORDINGS_DIR
            )

        shutil.copytree(
            backup_recordings,
            RECORDINGS_DIR,
        )


    # --------------------------------------------------------
    # RESTORE AUDIT DATA
    # --------------------------------------------------------

    backup_audit = (
        backup_dir
        / "audit"
    )

    if backup_audit.exists():

        if AUDIT_DIR.exists():

            shutil.rmtree(
                AUDIT_DIR
            )

        shutil.copytree(
            backup_audit,
            AUDIT_DIR,
        )


    return {
        "success": True,
        "restored_backup_id": (
            backup_id
        ),
        "safety_backup_id": (
            safety_backup.get(
                "backup_id"
            )
        ),
    }
