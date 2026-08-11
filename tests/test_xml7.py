from commercialrchproxy.rch.xml7 import analyze_xml_copy


def test_secure_xml_copy_is_parsed_but_not_claimed_as_xml7() -> None:
    analysis = analyze_xml_copy(b'<?xml version="1.0"?><receipt><line>Prodotto 0,00</line></receipt>')
    assert analysis.candidate_found is True
    assert analysis.well_formed_generic is True
    assert analysis.xml7_confirmed is False
    assert analysis.root_qname == "receipt"
    assert analysis.root_local_name == "receipt"
    assert analysis.fields[0].qname_path == "/receipt/line"


def test_namespace_qnames_and_candidate_offsets_are_preserved() -> None:
    payload = (
        b'\x02prefix<?xml version="1.0"?><r:receipt xmlns:r="urn:rch:test"><r:line>x</r:line></r:receipt>suffix\x03'
    )
    analysis = analyze_xml_copy(payload)
    assert analysis.candidate_found is True
    assert analysis.well_formed_generic is True
    assert analysis.xml7_confirmed is False
    assert analysis.candidate_start == payload.index(b"<?xml")
    assert analysis.candidate_end == payload.rfind(b">") + 1
    assert analysis.root_qname == "{urn:rch:test}receipt"
    assert analysis.root_local_name == "receipt"
    assert analysis.fields[0].qname_path == "/{urn:rch:test}receipt/{urn:rch:test}line"


def test_doctype_and_entity_are_rejected() -> None:
    payload = b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
    analysis = analyze_xml_copy(payload)
    assert analysis.candidate_found is True
    assert analysis.well_formed_generic is False
    assert analysis.error == "DTD_or_entity_declaration_rejected"


def test_malformed_xml_never_blocks_capture_analysis() -> None:
    analysis = analyze_xml_copy(b"<receipt><broken></receipt>")
    assert analysis.candidate_found is True
    assert analysis.well_formed_generic is False
    assert analysis.error


def test_binary_payload_has_no_forced_xml_interpretation() -> None:
    analysis = analyze_xml_copy(bytes(range(32)))
    assert analysis.candidate_found is False
    assert analysis.well_formed_generic is False
    assert analysis.xml7_confirmed is False


def test_generic_xml_depth_limit_is_reported_without_xml7_claim() -> None:
    payload = b"<n>" * 129 + b"value" + b"</n>" * 129
    analysis = analyze_xml_copy(payload)
    assert analysis.candidate_found is True
    assert analysis.well_formed_generic is True
    assert analysis.xml7_confirmed is False
    assert analysis.root_qname == "n"
    assert analysis.error == "xml_depth_limit_exceeded:128"
    assert analysis.fields == ()
