import unittest

from tools.architecture_handoff.protocol_metadata import (
    ALL_PROTOCOL_LABELS,
    MetadataState,
    PROTOCOL_MARKER,
    ProtocolMetadata,
    parse_protocol_block,
    render_protocol_block,
    validate_protocol_labels,
)
from tools.architecture_handoff.write_models import (
    ProtocolItemKind,
    RelationKind,
    TypedRelation,
)


class ProtocolMetadataTests(unittest.TestCase):
    def test_closed_vocabulary_contains_exactly_fifteen_labels(self):
        self.assertEqual(len(ALL_PROTOCOL_LABELS), 15)
        self.assertIn("return-kind:evidence-result", ALL_PROTOCOL_LABELS)
        self.assertIn("intake-state:pending", ALL_PROTOCOL_LABELS)

    def test_metadata_round_trip_preserves_forward_fields(self):
        metadata = ProtocolMetadata(
            schema_version=2,
            logical_target="example-implementation",
            relations=(
                TypedRelation(
                    RelationKind.IMPLEMENTATION,
                    "ADR-0003",
                    "a" * 40,
                ),
            ),
            correlation_id="corr-12",
            capability="account-address-prediction",
            expected_outcome="Return one deterministic address",
        )

        parsed = parse_protocol_block(render_protocol_block(metadata))

        self.assertIs(parsed.state, MetadataState.VERIFIED)
        self.assertEqual(parsed.metadata, metadata)

    def test_line_scalars_reject_values_that_cannot_round_trip(self):
        valid = {
            "schema_version": 2,
            "logical_target": "example-implementation",
            "correlation_id": "corr-12",
            "capability": "account-address-prediction",
            "expected_outcome": "Return one deterministic address",
        }
        invalid_values = (
            " leading",
            "trailing ",
            "carriage\rreturn",
            "line\nfeed",
            f"embedded {PROTOCOL_MARKER}",
            "embedded --> delimiter",
        )

        for field in (
            "logical_target",
            "correlation_id",
            "capability",
            "expected_outcome",
        ):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(
                        ValueError,
                        field.replace("_", "-"),
                    ):
                        render_protocol_block(
                            ProtocolMetadata(
                                **{**valid, field: value}
                            )
                        )

    def test_parser_does_not_normalize_carriage_return_in_scalar(self):
        parsed = parse_protocol_block(
            "<!-- architecture-handoff-protocol\n"
            "schema-version: 2\n"
            "logical-target: example-implementation\r\n"
            "-->"
        )

        self.assertIs(parsed.state, MetadataState.MALFORMED)
        self.assertIn("logical-target", parsed.limitation)

    def test_missing_legacy_block_is_unknown_not_inferred(self):
        parsed = parse_protocol_block("Human-readable Issue body")

        self.assertIs(parsed.state, MetadataState.MISSING)
        self.assertIsNone(parsed.metadata)
        self.assertIsNotNone(parsed.limitation)

    def test_structurally_valid_unversioned_legacy_block_is_missing(self):
        parsed = parse_protocol_block(
            "\n".join(
                (
                    "Legacy body.",
                    "",
                    "<!-- architecture-handoff-protocol",
                    "correlation-id: corr-12",
                    (
                        "relation: "
                        '{"kind":"refinement","revision":"abc123",'
                        '"target":"git:https://github.com/owner/docs:'
                        'architecture/09-architecture-decisions.md#adr-0003"}'
                    ),
                    "-->",
                )
            )
        )

        self.assertIs(parsed.state, MetadataState.MISSING)
        self.assertIsNone(parsed.metadata)
        self.assertIn("legacy unversioned", parsed.limitation)

    def test_invalid_legacy_shaped_block_remains_malformed(self):
        parsed = parse_protocol_block(
            "\n".join(
                (
                    "<!-- architecture-handoff-protocol",
                    "correlation-id: corr-12",
                    "relation: {bad json}",
                    "-->",
                )
            )
        )

        self.assertIs(parsed.state, MetadataState.MALFORMED)
        self.assertIn("malformed relation JSON", parsed.limitation)

    def test_v2_shaped_block_without_required_schema_remains_malformed(self):
        parsed = parse_protocol_block(
            "\n".join(
                (
                    "<!-- architecture-handoff-protocol",
                    "logical-target: example-implementation",
                    "-->",
                )
            )
        )

        self.assertIs(parsed.state, MetadataState.MALFORMED)
        self.assertIn("missing schema-version", parsed.limitation)

    def test_malformed_block_has_explicit_limitation(self):
        parsed = parse_protocol_block(
            "<!-- architecture-handoff-protocol\n"
            "schema-version: 2\n"
            "logical-target: example-implementation\n"
        )

        self.assertIs(parsed.state, MetadataState.MALFORMED)
        self.assertIsNone(parsed.metadata)
        self.assertTrue(parsed.limitation)

    def test_parser_rejects_duplicate_scalar_and_relation_values(self):
        relation = (
            'relation: {"kind":"refinement","revision":null,'
            '"target":"ADR-0003"}'
        )
        for body, expected in (
            (
                "\n".join(
                    (
                        "<!-- architecture-handoff-protocol",
                        "schema-version: 2",
                        "logical-target: example-implementation",
                        "logical-target: another-target",
                        "-->",
                    )
                ),
                "duplicate logical-target",
            ),
            (
                "\n".join(
                    (
                        "<!-- architecture-handoff-protocol",
                        "schema-version: 2",
                        "logical-target: example-implementation",
                        relation,
                        relation,
                        "-->",
                    )
                ),
                "duplicate relation",
            ),
        ):
            with self.subTest(expected=expected):
                parsed = parse_protocol_block(body)
                self.assertIs(parsed.state, MetadataState.MALFORMED)
                self.assertIn(expected, parsed.limitation)

    def test_parser_rejects_unsupported_schema_malformed_json_and_blanks(self):
        for line, expected in (
            ("schema-version: 3", "unsupported schema version"),
            ("relation: {bad json}", "malformed relation JSON"),
            ("logical-target:  ", "blank logical-target"),
        ):
            lines = [
                "<!-- architecture-handoff-protocol",
                "schema-version: 2",
                "logical-target: example-implementation",
                "-->",
            ]
            if line.startswith("schema-version"):
                lines[1] = line
            elif line.startswith("logical-target"):
                lines[2] = line
            else:
                lines.insert(3, line)
            parsed = parse_protocol_block("\n".join(lines))
            self.assertIs(parsed.state, MetadataState.MALFORMED)
            self.assertIn(expected, parsed.limitation)

    def test_parser_rejects_duplicate_relation_json_keys(self):
        parsed = parse_protocol_block(
            "\n".join(
                (
                    "<!-- architecture-handoff-protocol",
                    "schema-version: 2",
                    "logical-target: example-implementation",
                    'relation: {"kind":"refinement","revision":null,'
                    '"target":"ADR-0003","target":"ADR-0004"}',
                    "-->",
                )
            )
        )

        self.assertIs(parsed.state, MetadataState.MALFORMED)
        self.assertIn("duplicate relation JSON key", parsed.limitation)

    def test_duplicate_family_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "multiple status labels"):
            validate_protocol_labels(("status:draft", "status:ready"))

    def test_closed_vocabulary_and_item_kind_rules_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "unsupported status label"):
            validate_protocol_labels(("status:invented",))
        with self.assertRaisesRegex(ValueError, "target-native internal"):
            validate_protocol_labels(("work-route:target-native-internal",))
        with self.assertRaisesRegex(ValueError, "work item"):
            validate_protocol_labels(
                ("return-kind:evidence-result",),
                item_kind=ProtocolItemKind.WORK_ITEM,
            )
        with self.assertRaisesRegex(ValueError, "Return Item"):
            validate_protocol_labels(
                ("status:draft",),
                item_kind=ProtocolItemKind.RETURN_ITEM,
            )
