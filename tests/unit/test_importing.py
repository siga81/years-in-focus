from __future__ import annotations

from pathlib import Path

from facemovie.importing import scan_import_folder, scan_import_paths


def test_scan_import_folder_reports_tagged_and_untagged_images(tmp_path: Path) -> None:
    tagged = tmp_path / "tagged.jpg"
    tagged.write_text("""<x:xmpmeta xmlns:x='adobe:ns:meta/' xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:RDF><rdf:Description xmlns:MPReg='http://ns.microsoft.com/photo/1.2/t/Region#'>
    <MPReg:PersonDisplayName>Anna</MPReg:PersonDisplayName>
    </rdf:Description></rdf:RDF></x:xmpmeta>""", encoding="utf-8")
    untagged = tmp_path / "untagged.jpeg"
    untagged.write_bytes(b"not tagged")
    (tmp_path / "ignore.png").write_bytes(b"ignored")
    result = scan_import_folder(tmp_path)
    assert len(result.image_files) == 2
    assert result.person_counts == {"Anna": 1}
    assert result.untagged_files == (untagged,)


def test_scan_import_paths_uses_only_selected_images(tmp_path: Path) -> None:
    selected = tmp_path / "selected.jpg"
    selected.write_bytes(b"no tags")
    unselected = tmp_path / "unselected.jpg"
    unselected.write_bytes(b"no tags")
    result = scan_import_paths((selected,))
    assert result.image_files == (selected,)
