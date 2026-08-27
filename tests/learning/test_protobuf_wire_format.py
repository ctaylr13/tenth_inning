"""One-time wire-format inspection; production decoding stays generated."""

from artifacts import game_artifact_pb2


def _varint(payload: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7


def _wire_fields(payload: bytes) -> list[tuple[int, int, int, int, int, object]]:
    """Return field/wire type plus tag, value, and end offsets for inspection."""
    fields = []
    offset = 0
    while offset < len(payload):
        tag_offset = offset
        tag, offset = _varint(payload, offset)
        field_number, wire_type = tag >> 3, tag & 0b111
        if wire_type == 0:
            value_offset = offset
            value, offset = _varint(payload, offset)
        elif wire_type == 2:
            size, offset = _varint(payload, offset)
            value_offset = offset
            value = payload[offset : offset + size]
            offset += size
        else:
            raise AssertionError(
                f"This learning fixture did not expect wire type {wire_type}."
            )
        fields.append(
            (field_number, wire_type, tag_offset, value_offset, offset, value)
        )
    return fields


def test_inspect_raw_wire_bytes_and_offsets_once():
    artifact = game_artifact_pb2.GameArtifact(schema_version=1)
    artifact.metadata.game_pk = 150
    artifact.metadata.official_date = "x"

    raw = artifact.SerializeToString(deterministic=True)

    # 08 = field 1/varint; 12 = field 2/length-delimited. 150 needs two
    # varint bytes (96 01). The offsets make the framing boundaries concrete.
    assert raw.hex(" ") == "08 01 12 06 08 96 01 12 01 78"
    top_level = _wire_fields(raw)
    assert top_level == [
        (1, 0, 0, 1, 2, 1),
        (2, 2, 2, 4, 10, b"\x08\x96\x01\x12\x01x"),
    ]
    assert _wire_fields(top_level[1][5]) == [
        (1, 0, 0, 1, 3, 150),
        (2, 2, 3, 5, 6, b"x"),
    ]

    # The actual application path delegates all decoding to generated code.
    assert game_artifact_pb2.GameArtifact.FromString(raw) == artifact
