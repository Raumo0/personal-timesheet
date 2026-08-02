import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.lifecycle import (  # noqa: E402
    validate_brief_transition,
)
from tools.architecture_handoff.models import WorkRoute  # noqa: E402
from tools.architecture_handoff.write_models import (  # noqa: E402
    IntakeState,
    ProtocolItemKind,
    RelationKind,
    ReturnKind,
    TypedRelation,
    WriteIntent,
    WriteOperation,
    validate_intent,
)


def source_relation():
    return TypedRelation(
        kind=RelationKind.REFINEMENT,
        target="git:owner/documentation@abc123:ADR-0003",
        revision="abc123",
    )


def brief_intent(**overrides):
    values = {
        "operation": WriteOperation.CREATE,
        "target_key": "example-implementation",
        "item_kind": ProtocolItemKind.WORK_ITEM,
        "title": "Verify deterministic address lookup",
        "body": "One bounded outcome.",
        "route": WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
        "lifecycle_state": "draft",
        "relations": (source_relation(),),
    }
    values.update(overrides)
    return WriteIntent(**values)


class WriteModelTests(unittest.TestCase):
    def test_brief_create_requires_draft_and_direct_relation(self):
        with self.assertRaisesRegex(
            ValueError,
            "direct typed relation",
        ):
            validate_intent(brief_intent(relations=()))

        with self.assertRaisesRegex(
            ValueError,
            "must start as draft",
        ):
            validate_intent(brief_intent(lifecycle_state="ready"))

        validate_intent(brief_intent())

    def test_documentation_write_rejects_target_native_internal_route(self):
        with self.assertRaisesRegex(
            ValueError,
            "target-native internal work",
        ):
            validate_intent(
                brief_intent(route=WorkRoute.TARGET_NATIVE_INTERNAL)
            )

    def test_update_requires_provider_identity_and_expected_state(self):
        with self.assertRaisesRegex(
            ValueError,
            "provider_id and expected_provider_state",
        ):
            validate_intent(
                brief_intent(
                    operation=WriteOperation.UPDATE,
                    lifecycle_state="ready",
                )
            )

        validate_intent(
            brief_intent(
                operation=WriteOperation.UPDATE,
                lifecycle_state="ready",
                previous_lifecycle_state="draft",
                provider_id="11",
                expected_provider_state="2026-07-30T10:00:00Z",
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "previous_lifecycle_state",
        ):
            validate_intent(
                brief_intent(
                    operation=WriteOperation.UPDATE,
                    lifecycle_state="ready",
                    provider_id="11",
                    expected_provider_state=(
                        "2026-07-30T10:00:00Z"
                    ),
                )
            )

        with self.assertRaisesRegex(
            ValueError,
            "invalid Brief lifecycle transition",
        ):
            validate_intent(
                brief_intent(
                    operation=WriteOperation.UPDATE,
                    lifecycle_state="done",
                    previous_lifecycle_state="draft",
                    provider_id="11",
                    expected_provider_state=(
                        "2026-07-30T10:00:00Z"
                    ),
                )
            )

    def test_create_rejects_provider_identity(self):
        with self.assertRaisesRegex(
            ValueError,
            "create intent must not carry provider state",
        ):
            validate_intent(
                brief_intent(
                    provider_id="11",
                    expected_provider_state="2026-07-30T10:00:00Z",
                )
            )

    def test_write_intent_is_immutable(self):
        intent = brief_intent()

        self.assertFalse(hasattr(intent, "native_labels"))
        with self.assertRaises(FrozenInstanceError):
            intent.title = "Changed"

    def test_brief_lifecycle_accepts_only_declared_transitions(self):
        validate_brief_transition("draft", "backlog")
        validate_brief_transition("draft", "ready")
        validate_brief_transition("ready", "in-progress")
        validate_brief_transition("in-progress", "in-review")
        validate_brief_transition("in-review", "done")
        validate_brief_transition("in-review", "backlog")

        for before, after in (
            ("draft", "done"),
            ("backlog", "in-progress"),
            ("ready", "done"),
            ("done", "ready"),
            ("cancelled", "draft"),
        ):
            with self.subTest(before=before, after=after):
                with self.assertRaisesRegex(
                    ValueError,
                    "invalid Brief lifecycle transition",
                ):
                    validate_brief_transition(before, after)

    def test_rejects_empty_core_strings_and_malformed_relations(self):
        with self.assertRaisesRegex(ValueError, "title"):
            validate_intent(brief_intent(title=" "))

        with self.assertRaisesRegex(ValueError, "relation target"):
            validate_intent(
                brief_intent(
                    relations=(
                        TypedRelation(
                            kind=RelationKind.REFINEMENT,
                            target="",
                        ),
                    )
                )
            )

    def test_optional_search_facets_must_be_non_empty_when_present(self):
        validate_intent(
            brief_intent(
                capability="account-address-prediction",
                expected_outcome="Return one deterministic address",
            )
        )
        for field in ("capability", "expected_outcome"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    validate_intent(brief_intent(**{field: " "}))

    def test_generic_return_intent_enforces_enum_and_transition(self):
        values = {
            "operation": WriteOperation.UPDATE,
            "target_key": "documentation-intake",
            "item_kind": ProtocolItemKind.RETURN_ITEM,
            "title": "Return evidence",
            "body": "Evidence.",
            "intake_state": IntakeState.HANDLED,
            "previous_intake_state": IntakeState.PENDING,
            "return_kind": ReturnKind.EVIDENCE_RESULT,
            "relations": (
                TypedRelation(
                    kind=RelationKind.RETURN,
                    target="github:owner/implementation#12",
                ),
            ),
            "correlation_id": "corr-12",
            "provider_id": "40",
            "expected_provider_state": "2026-07-30T11:00:00Z",
        }
        validate_intent(WriteIntent(**values))

        with self.assertRaisesRegex(
            ValueError,
            "return_kind must be a ReturnKind",
        ):
            validate_intent(
                WriteIntent(
                    **{**values, "return_kind": "evidence-result"}
                )
            )

        with self.assertRaisesRegex(
            ValueError,
            "pending to handled",
        ):
            validate_intent(
                WriteIntent(
                    **{
                        **values,
                        "previous_intake_state": IntakeState.HANDLED,
                    }
                )
            )

        with self.assertRaisesRegex(
            ValueError,
            "must not carry Brief lifecycle",
        ):
            validate_intent(
                WriteIntent(
                    **{**values, "lifecycle_state": "draft"}
                )
            )


if __name__ == "__main__":
    unittest.main()
