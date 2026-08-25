"""Read-only access to a digiKam database.

The adapter deliberately exposes only the data Years in Focus needs: confirmed person
tags, image paths and their tagged face rectangles.  It never writes to digiKam.
SQLite is available without an extra package; MariaDB uses the optional pure-Python
``PyMySQL`` driver so the standalone bundle has no dependency on a local mysql.exe.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from facemovie.models import FaceRegion

DatabaseType = Literal["mariadb", "sqlite"]


@dataclass(frozen=True)
class DigiKamConnection:
    database_type: DatabaseType
    database: str
    host: str = "127.0.0.1"
    port: int = 3307
    user: str = "root"
    password: str = ""
    collection_root: str = ""


@dataclass(frozen=True)
class DigiKamDiscovery:
    """A locally discovered digiKam database connection, without its password."""

    connection: DigiKamConnection
    config_path: Path
    internal_server: bool
    has_encrypted_password: bool


@dataclass(frozen=True)
class DigiKamPerson:
    tag_id: int
    name: str
    image_count: int


@dataclass(frozen=True)
class DigiKamImage:
    path: Path
    region: FaceRegion
    collection_subpath: str


def discover_digikam_connection(config_paths: Iterable[Path] | None = None) -> DigiKamDiscovery | None:
    """Read the standard digiKam config locations without displaying credentials.

    digiKam stores an encrypted password in its config. YiF deliberately does not
    decrypt or persist it; password-protected databases still use the manual expert
    path after discovery.
    """
    if config_paths is None:
        candidates: list[Path] = []
        for variable in ("LOCALAPPDATA", "APPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.append(Path(root) / "digikamrc")
        candidates.extend((Path.home() / ".config" / "digikamrc", Path.home() / ".config" / "digikam" / "digikamrc"))
    else:
        candidates = list(config_paths)
    for path in candidates:
        discovery = _read_digikamrc(path)
        if discovery is not None:
            return discovery
    return None


def _read_digikamrc(path: Path) -> DigiKamDiscovery | None:
    """Parse just digiKam's [Database Settings] KConfig group."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    values: dict[str, str] = {}
    in_database_section = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_database_section = line[1:-1].casefold() == "database settings"
            continue
        if not in_database_section or not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().casefold()] = value.strip()
    database = values.get("database name", "")
    database_type = values.get("database type", "").casefold()
    if not database:
        return None
    is_sqlite = database_type in {"qsqlite", "sqlite"}
    internal_server = values.get("internal database server", "").casefold() == "true"
    try:
        port = int(values.get("database port") or ("3307" if internal_server else "3306"))
    except ValueError:
        port = 3307 if internal_server else 3306
    connection = DigiKamConnection(
        "sqlite" if is_sqlite else "mariadb",
        database,
        values.get("database hostname") or "127.0.0.1",
        port,
        values.get("database username") or "root",
    )
    return DigiKamDiscovery(
        connection=connection,
        config_path=path,
        internal_server=internal_server,
        has_encrypted_password=bool(values.get("database encrypted password")),
    )


class _Cursor(Protocol):
    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def fetchone(self) -> Any: ...
    def close(self) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...
    def close(self) -> None: ...


def _connect(settings: DigiKamConnection) -> _Connection:
    if settings.database_type == "sqlite":
        path = Path(settings.database).expanduser()
        if not path.is_file():
            raise ValueError("Die gewählte digiKam-SQLite-Datei existiert nicht.")
        # URI mode=ro prevents accidental creation or modification of the database.
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection
    try:
        import pymysql  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError(
            "Für MariaDB fehlt PyMySQL. Die Windows-Standalone-Version liefert es mit; "
            "in der Entwicklungsumgebung bitte 'python -m pip install -e .[digikam]' ausführen."
        ) from error
    return pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=20,
        write_timeout=20,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _placeholder(settings: DigiKamConnection) -> str:
    return "?" if settings.database_type == "sqlite" else "%s"


def _rows(cursor: _Cursor) -> Iterator[dict[str, Any]]:
    for row in cursor.fetchall():
        if isinstance(row, dict):
            yield row
        else:
            yield {key: row[key] for key in row.keys()}


def test_connection(settings: DigiKamConnection) -> str:
    """Validate a connection with a harmless read-only query and return its version."""
    with closing(_connect(settings)) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT sqlite_version() AS version" if settings.database_type == "sqlite" else "SELECT VERSION() AS version")
            row = cursor.fetchone()
        finally:
            cursor.close()
    if isinstance(row, dict):
        return str(row["version"])
    return str(row[0])


def list_people(settings: DigiKamConnection) -> list[DigiKamPerson]:
    """List confirmed digiKam person tags with active image-region counts."""
    marker = _placeholder(settings)
    name_order = "name COLLATE NOCASE" if settings.database_type == "sqlite" else "name"
    query = f"""
        SELECT t.id AS tag_id, t.name AS name, COUNT(DISTINCT p.imageid) AS image_count
        FROM tags t
        JOIN tagproperties person ON person.tagid=t.id AND person.property='person'
        JOIN imagetagproperties p ON p.tagid=t.id AND p.property='tagRegion'
        JOIN images i ON i.id=p.imageid AND i.status=1
        WHERE NOT EXISTS (
            SELECT 1 FROM tagproperties sys
            WHERE sys.tagid=t.id
              AND sys.property IN ('unknownPerson', 'ignoredPerson', 'unconfirmedPerson')
        )
        GROUP BY t.id, t.name
        HAVING COUNT(DISTINCT p.imageid) > {marker}
        ORDER BY image_count DESC, {name_order}
    """
    with closing(_connect(settings)) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(query, (0,))
            return [
                DigiKamPerson(int(row["tag_id"]), str(row["name"]), int(row["image_count"]))
                for row in _rows(cursor)
            ]
        finally:
            cursor.close()


def _absolute_path(collection_root: str | Path, specific_path: str, relative: str, filename: str) -> Path:
    # digiKam stores separator-normalized album paths; lstrip avoids Path treating
    # a leading slash as a new drive/root on Windows.
    root = Path(collection_root).expanduser()
    parts = [part for part in specific_path.replace("\\", "/").split("/") if part]
    album_parts = [part for part in relative.replace("\\", "/").split("/") if part]
    if parts and len(root.parts) >= len(parts):
        tail = root.parts[-len(parts):]
        if all(left.casefold() == right.casefold() for left, right in zip(tail, parts)):
            return root.joinpath(*album_parts, filename)
    return root.joinpath(*parts, *album_parts, filename)


def person_collection_subpaths(settings: DigiKamConnection, person: DigiKamPerson) -> list[str]:
    """Return the digiKam album-root portions needed to guide path selection."""
    marker = _placeholder(settings)
    query = f"""
        SELECT DISTINCT ar.specificPath AS specific_path
        FROM imagetagproperties p
        JOIN images i ON i.id=p.imageid AND i.status=1
        JOIN albums a ON a.id=i.album
        JOIN albumroots ar ON ar.id=a.albumRoot AND ar.status=0
        WHERE p.tagid={marker} AND p.property='tagRegion'
        ORDER BY specific_path
    """
    with closing(_connect(settings)) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(query, (person.tag_id,))
            return [str(row["specific_path"]) for row in _rows(cursor)]
        finally:
            cursor.close()


def person_images(
    settings: DigiKamConnection,
    person: DigiKamPerson,
    collection_root: Path | Mapping[str, Path],
    *,
    all_regions: bool = False,
) -> list[DigiKamImage]:
    """Return JPG/JPEG images and pixel-space face rectangles for one person.

    The normal picker returns one item per photo.  Incremental project updates
    can request every confirmed region, because a photo may contain the same
    person more than once and the previously selected face must be checked.
    """
    marker = _placeholder(settings)
    query = f"""
        SELECT i.id AS image_id, p.value AS rect_xml, i.name AS filename, a.relativePath AS relative_path,
               ar.specificPath AS root_path
        FROM imagetagproperties p
        JOIN images i ON i.id=p.imageid AND i.status=1
        JOIN albums a ON a.id=i.album
        JOIN albumroots ar ON ar.id=a.albumRoot AND ar.status=0
        WHERE p.tagid={marker} AND p.property='tagRegion'
        ORDER BY i.id
    """
    from xml.etree import ElementTree

    result: list[DigiKamImage] = []
    seen_image_ids: set[int] = set()
    with closing(_connect(settings)) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(query, (person.tag_id,))
            rows = list(_rows(cursor))
        finally:
            cursor.close()
    for row in rows:
        image_id = int(row["image_id"])
        # digiKam can retain more than one tagRegion row for a person on the
        # same photo. The person picker intentionally reports distinct photos,
        # so a storyboard must use that identical definition as well.
        if not all_regions and image_id in seen_image_ids:
            continue
        specific_path = str(row["root_path"])
        if isinstance(collection_root, Mapping):
            root = collection_root.get(specific_path)
            if root is None:
                # The caller presents a targeted mapping dialog before import.
                # Keep this row unreachable rather than guessing a filesystem path.
                continue
        else:
            root = collection_root
        path = _absolute_path(
            root, specific_path, str(row["relative_path"]), str(row["filename"])
        )
        if path.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        try:
            rect = ElementTree.fromstring(str(row["rect_xml"]))
            x = float(rect.attrib["x"])
            y = float(rect.attrib["y"])
            width = float(rect.attrib["width"])
            height = float(rect.attrib["height"])
            if width <= 0 or height <= 0:
                continue
            region = FaceRegion(
                person.name,
                x, y, width, height,
                "pixel_left_top",
                "digikam_database",
            )
        except (ElementTree.ParseError, KeyError, ValueError):
            continue
        result.append(DigiKamImage(path, region, specific_path))
        if not all_regions:
            seen_image_ids.add(image_id)
    return result


def same_face_region(left: FaceRegion, right: FaceRegion, *, tolerance: float = 0.01) -> bool:
    """Compare two digiKam rectangles while accepting insignificant rounding."""
    return (
        left.coordinate_system == right.coordinate_system
        and all(
            abs(first - second) <= tolerance
            for first, second in zip(
                (left.x, left.y, left.width, left.height),
                (right.x, right.y, right.width, right.height),
            )
        )
    )
