from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from facemovie.digikam import (
    DigiKamConnection,
    discover_digikam_connection,
    list_people,
    person_collection_subpaths,
    person_images,
    test_connection as database_test_connection,
)
from facemovie.importing import paths_from_input_list
from facemovie.project import StoryboardProject


class DigiKamSqliteAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.collection = root / "collection"
        image = self.collection / "Photos" / "2026" / "portrait.JPG"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"The adapter only resolves paths; decoding is done by analysis.")
        self.database = root / "digikam.db"
        connection = sqlite3.connect(self.database)
        connection.executescript(
            """
            CREATE TABLE tags (id INTEGER, name TEXT);
            CREATE TABLE tagproperties (tagid INTEGER, property TEXT);
            CREATE TABLE imagetagproperties (imageid INTEGER, tagid INTEGER, property TEXT, value TEXT);
            CREATE TABLE images (id INTEGER, album INTEGER, name TEXT, status INTEGER);
            CREATE TABLE albums (id INTEGER, albumRoot INTEGER, relativePath TEXT);
            CREATE TABLE albumroots (id INTEGER, status INTEGER, specificPath TEXT);
            INSERT INTO tags VALUES (7, 'Test Person');
            INSERT INTO tagproperties VALUES (7, 'person');
            INSERT INTO images VALUES (11, 4, 'portrait.JPG', 1);
            INSERT INTO albums VALUES (4, 2, '/2026');
            INSERT INTO albumroots VALUES (2, 0, '/Photos');
            INSERT INTO imagetagproperties VALUES
              (11, 7, 'tagRegion', '<rect x="100" y="200" width="300" height="400"/>');
            """
        )
        connection.commit()
        connection.close()
        self.settings = DigiKamConnection("sqlite", str(self.database))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lists_person_and_resolves_region_path(self) -> None:
        self.assertTrue(database_test_connection(self.settings))
        people = list_people(self.settings)
        self.assertEqual([(person.tag_id, person.name, person.image_count) for person in people], [(7, "Test Person", 1)])
        self.assertEqual(person_collection_subpaths(self.settings, people[0]), ["/Photos"])
        images = person_images(self.settings, people[0], self.collection)
        self.assertEqual(images[0].path, self.collection / "Photos" / "2026" / "portrait.JPG")
        direct_images = person_images(self.settings, people[0], self.collection / "Photos")
        self.assertEqual(direct_images[0].path, images[0].path)
        mapped_images = person_images(self.settings, people[0], {"/Photos": self.collection})
        self.assertEqual(mapped_images[0].path, images[0].path)
        self.assertEqual(images[0].region.coordinate_system, "pixel_left_top")
        self.assertEqual(images[0].region.x, 100)
        self.assertEqual(images[0].region.height, 400)
        self.assertEqual(images[0].region.source, "digikam_database")

    def test_input_list_is_read_without_expanding_the_command_line(self) -> None:
        manifest = Path(self.temporary.name) / "bilder.json"
        image_paths = [Path(self.temporary.name) / f"bild-{index}.jpg" for index in range(500)]
        manifest.write_text(json.dumps({"images": [str(path) for path in image_paths]}), encoding="utf-8")
        self.assertEqual(paths_from_input_list(manifest), [path.resolve() for path in image_paths])

    def test_discovers_mariadb_settings_from_digikamrc_without_password(self) -> None:
        config = Path(self.temporary.name) / "digikamrc"
        config.write_text(
            """[Database Settings]\nDatabase Type=QMYSQL\nDatabase Hostname=localhost\nDatabase Port=3307\nDatabase Username=root\nDatabase Name=digikam\nDatabase Encrypted Password=encrypted-placeholder\nInternal Database Server=true\n""",
            encoding="utf-8",
        )
        discovery = discover_digikam_connection([config])
        self.assertIsNotNone(discovery)
        assert discovery is not None
        self.assertEqual(discovery.connection, DigiKamConnection("mariadb", "digikam", "localhost", 3307, "root"))
        self.assertTrue(discovery.internal_server)
        self.assertTrue(discovery.has_encrypted_password)
        self.assertEqual(discovery.connection.password, "")

    def test_duplicate_regions_for_one_photo_produce_one_storyboard_card(self) -> None:
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO imagetagproperties VALUES (11, 7, 'tagRegion', '<rect x=\"110\" y=\"210\" width=\"300\" height=\"400\"/>')"
        )
        connection.commit()
        connection.close()
        person = list_people(self.settings)[0]
        self.assertEqual(person.image_count, 1)
        images = person_images(self.settings, person, self.collection)
        self.assertEqual(len(images), 1)

    def test_new_projects_sort_records_by_capture_time(self) -> None:
        records = [
            {"path": "C:/images/undated.jpg"},
            {"path": "C:/images/later.jpg", "capture_time": "2024-08-02T10:00:00"},
            {"path": "C:/images/earlier.jpg", "capture_time": "2021-01-02T10:00:00"},
        ]
        ordered = StoryboardProject.sorted_records(records, "date")
        self.assertEqual([Path(record["path"]).name for record in ordered], ["earlier.jpg", "later.jpg", "undated.jpg"])


if __name__ == "__main__":
    unittest.main()
