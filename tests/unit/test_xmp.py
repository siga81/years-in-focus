from __future__ import annotations

from facemovie.metadata.xmp import person_names_from_xmp_text, regions_from_xmp_text


def test_finds_microsoft_photo_region() -> None:
    xmp = """<x:xmpmeta xmlns:x='adobe:ns:meta/' xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:RDF><rdf:Description xmlns:MPReg='http://ns.microsoft.com/photo/1.2/t/Region#'>
    <MPReg:PersonDisplayName>Test Person</MPReg:PersonDisplayName>
    <MPReg:Rectangle>0.2, 0.3, 0.1, 0.2</MPReg:Rectangle>
    </rdf:Description></rdf:RDF></x:xmpmeta>"""
    regions = regions_from_xmp_text(xmp, "Test Person")
    assert len(regions) == 1
    assert regions[0].source == "microsoft_photo"
    assert regions[0].x == 0.2
    assert regions[0].height == 0.2


def test_finds_digikam_mwg_child_name_region() -> None:
    xmp = """<x:xmpmeta xmlns:x='adobe:ns:meta/' xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:RDF><rdf:Description xmlns:mwg-rs='http://www.metadataworkinggroup.com/schemas/regions/' xmlns:stArea='http://ns.adobe.com/xmp/sType/Area#'>
    <mwg-rs:Regions><mwg-rs:RegionList><rdf:Bag><rdf:li>
    <mwg-rs:Area stArea:x='0.5' stArea:y='0.4' stArea:w='0.2' stArea:h='0.3'/><mwg-rs:Name>Laura</mwg-rs:Name>
    </rdf:li></rdf:Bag></mwg-rs:RegionList></mwg-rs:Regions>
    </rdf:Description></rdf:RDF></x:xmpmeta>"""
    regions = regions_from_xmp_text(xmp, "Laura")
    assert len(regions) == 1
    assert regions[0].source == "mwg"
    assert person_names_from_xmp_text(xmp) == ["Laura"]


def test_lists_distinct_people_from_xmp() -> None:
    xmp = """<x:xmpmeta xmlns:x='adobe:ns:meta/' xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
    <rdf:RDF><rdf:Description xmlns:MPReg='http://ns.microsoft.com/photo/1.2/t/Region#'>
    <MPReg:PersonDisplayName>Anna</MPReg:PersonDisplayName>
    <MPReg:PersonDisplayName>Bernd</MPReg:PersonDisplayName>
    <MPReg:PersonDisplayName>Anna</MPReg:PersonDisplayName>
    </rdf:Description></rdf:RDF></x:xmpmeta>"""
    assert person_names_from_xmp_text(xmp) == ["Anna", "Bernd"]
