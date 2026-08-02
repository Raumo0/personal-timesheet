import json
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.github import (  # noqa: E402
    AdapterError,
    GitHubRestTransport,
)
from tools.architecture_handoff.github_write import (  # noqa: E402
    GitHubWriteAdapter,
)
from tools.architecture_handoff.models import WorkRoute  # noqa: E402
from tools.architecture_handoff.protocol_metadata import (  # noqa: E402
    MetadataState,
    parse_protocol_block,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    StoreConfig,
    StoreRole,
    TargetConfig,
)
from tools.architecture_handoff.runtime_config import QueryBudget  # noqa: E402
from tools.architecture_handoff.write_coordinator import (  # noqa: E402
    CandidateDisposition,
    WriteCoordinator,
    WriteTargetConfig,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    IntakeState,
    ProtocolItemKind,
    RelationKind,
    TypedRelation,
    ReturnKind,
    WriteIntent,
    WriteOperation,
)


def github_target():
    return TargetConfig(
        key="example-implementation",
        provider="github",
        repository="owner/repository",
        routing_status="active",
        owns=("pilot implementation",),
        excludes=(),
    )


def github_intake_store():
    return StoreConfig(
        key="documentation-intake",
        role=StoreRole.DOCUMENTATION_INTAKE,
        provider="github",
        repository="owner/docs",
        routing_status="active",
        tracker_reference="github:owner/docs",
    )


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class FakeWriteTransport:
    def __init__(self, record):
        self.record = record
        self.calls = []

    def get(self, path, params):
        self.calls.append(("GET", path, params))
        return dict(self.record), None

    def post(self, path, payload):
        self.calls.append(("POST", path, payload))
        self.record.update(payload)
        return dict(self.record), None

    def patch(self, path, payload):
        self.calls.append(("PATCH", path, payload))
        self.record.update(payload)
        return dict(self.record), None


def relation():
    return TypedRelation(
        kind=RelationKind.REFINEMENT,
        target="git:owner/docs@abc123:ADR-0003",
        revision="abc123",
    )


def brief_intent(**overrides):
    values = {
        "operation": WriteOperation.CREATE,
        "target_key": "example-implementation",
        "item_kind": ProtocolItemKind.WORK_ITEM,
        "title": "Verify deterministic lookup",
        "body": "One bounded outcome.",
        "route": WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
        "lifecycle_state": "draft",
        "relations": (relation(),),
    }
    values.update(overrides)
    return WriteIntent(**values)


def github_record(**overrides):
    values = {
        "number": 11,
        "title": "Verify deterministic lookup",
        "body": "One bounded outcome.",
        "labels": [
            {"name": "status:draft"},
            {"name": "work-route:architecture-slice-handoff"},
        ],
        "updated_at": "2026-07-30T10:00:00Z",
        "html_url": "https://github.com/owner/repository/issues/11",
    }
    values.update(overrides)
    return values


class GitHubWriteTests(unittest.TestCase):
    def test_post_sends_json_with_bounded_timeout(self):
        observed = {}

        def opener(request, *, timeout):
            observed["method"] = request.get_method()
            observed["payload"] = json.loads(request.data.decode("utf-8"))
            observed["timeout"] = timeout
            observed["content_type"] = request.get_header("Content-type")
            return FakeResponse(github_record())

        transport = GitHubRestTransport(token="secret", opener=opener)
        payload, _ = transport.post(
            "repos/owner/repository/issues",
            {"title": "One title", "body": "One body"},
        )

        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["timeout"], 15)
        self.assertEqual(observed["content_type"], "application/json")
        self.assertEqual(observed["payload"]["title"], "One title")
        self.assertEqual(payload["number"], 11)

    def test_patch_sends_json_with_bounded_timeout(self):
        observed = {}

        def opener(request, *, timeout):
            observed["method"] = request.get_method()
            observed["payload"] = json.loads(request.data.decode("utf-8"))
            observed["timeout"] = timeout
            return FakeResponse(github_record())

        transport = GitHubRestTransport(opener=opener)
        transport.patch(
            "repos/owner/repository/issues/11",
            {"title": "Updated"},
        )

        self.assertEqual(observed["method"], "PATCH")
        self.assertEqual(observed["timeout"], 15)
        self.assertEqual(observed["payload"], {"title": "Updated"})

    def test_write_transport_rejects_non_json_payload_safely(self):
        transport = GitHubRestTransport(
            token="secret",
            opener=lambda *_args, **_kwargs: None,
        )

        with self.assertRaisesRegex(
            AdapterError,
            "GitHub request payload must be JSON-compatible",
        ) as context:
            transport.post(
                "repos/owner/repository/issues",
                {"unsafe": object()},
            )

        self.assertNotIn("secret", str(context.exception))

    def test_render_maps_route_and_lifecycle_labels_once(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )

        payload = adapter.render_payload(brief_intent())

        self.assertEqual(
            payload["labels"],
            [
                "status:draft",
                "work-route:architecture-slice-handoff",
            ],
        )
        self.assertIn('"kind":"refinement"', payload["body"])
        self.assertIn(
            '"target":"git:owner/docs@abc123:ADR-0003"',
            payload["body"],
        )
        parsed = parse_protocol_block(payload["body"])
        self.assertIs(parsed.state, MetadataState.VERIFIED)
        self.assertEqual(
            parsed.metadata.logical_target,
            "example-implementation",
        )

    def test_render_includes_optional_search_facets_in_protocol_block(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )

        payload = adapter.render_payload(
            brief_intent(
                capability="account-address-prediction",
                expected_outcome="Return one deterministic address",
            )
        )
        parsed = parse_protocol_block(payload["body"])

        self.assertIs(parsed.state, MetadataState.VERIFIED)
        self.assertEqual(
            parsed.metadata.capability,
            "account-address-prediction",
        )
        self.assertEqual(
            parsed.metadata.expected_outcome,
            "Return one deterministic address",
        )

    def test_render_maps_return_kind_and_intake_state(self):
        adapter = GitHubWriteAdapter(
            github_intake_store(),
            FakeWriteTransport(github_record()),
        )
        return_intent = WriteIntent(
            operation=WriteOperation.CREATE,
            target_key="documentation-intake",
            item_kind=ProtocolItemKind.RETURN_ITEM,
            title="Return evidence",
            body="Evidence body.",
            intake_state=IntakeState.PENDING,
            return_kind=ReturnKind.EVIDENCE_RESULT,
            relations=(
                TypedRelation(
                    kind=RelationKind.RETURN,
                    target="github:owner/implementation#12",
                ),
            ),
            correlation_id="corr-12",
        )

        payload = adapter.render_payload(return_intent)

        self.assertEqual(
            payload["labels"],
            [
                "intake-state:pending",
                "return-kind:evidence-result",
            ],
        )
        self.assertIn("correlation-id: corr-12", payload["body"])
        self.assertIn('"kind":"return"', payload["body"])

    def test_update_render_preserves_non_protocol_labels(self):
        record = github_record(
            labels=[
                {"name": "priority:high"},
                {"name": "status:draft"},
                {
                    "name": (
                        "work-route:"
                        "architecture-slice-handoff"
                    )
                },
            ]
        )
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(record),
        )

        payload = adapter.render_payload(
            brief_intent(
                operation=WriteOperation.UPDATE,
                lifecycle_state="ready",
                previous_lifecycle_state="draft",
                provider_id="11",
                expected_provider_state="2026-07-30T10:00:00Z",
            )
        )

        self.assertEqual(
            payload["labels"],
            [
                "priority:high",
                "status:ready",
                "work-route:architecture-slice-handoff",
            ],
        )

    def test_update_render_replaces_existing_protocol_metadata(self):
        transport = FakeWriteTransport(github_record())
        adapter = GitHubWriteAdapter(github_target(), transport)
        created_payload = adapter.render_payload(brief_intent())
        transport.record["body"] = created_payload["body"]

        updated_payload = adapter.render_payload(
            brief_intent(
                operation=WriteOperation.UPDATE,
                lifecycle_state="ready",
                previous_lifecycle_state="draft",
                provider_id="11",
                expected_provider_state="2026-07-30T10:00:00Z",
                body=created_payload["body"],
            )
        )

        self.assertEqual(
            updated_payload["body"].count(
                "<!-- architecture-handoff-protocol"
            ),
            1,
        )

    def test_create_uses_repository_issue_endpoint(self):
        transport = FakeWriteTransport(github_record())
        adapter = GitHubWriteAdapter(github_target(), transport)
        payload = adapter.render_payload(brief_intent())

        created = adapter.create_item(payload)

        self.assertEqual(
            transport.calls[0],
            (
                "POST",
                "repos/owner/repository/issues",
                payload,
            ),
        )
        self.assertEqual(created["number"], 11)

    def test_update_rejects_changed_expected_provider_state(self):
        transport = FakeWriteTransport(github_record())
        adapter = GitHubWriteAdapter(github_target(), transport)
        update_intent = brief_intent(
            operation=WriteOperation.UPDATE,
            lifecycle_state="ready",
            previous_lifecycle_state="draft",
            provider_id="11",
            expected_provider_state="2026-07-30T09:00:00Z",
        )

        with self.assertRaisesRegex(
            AdapterError,
            "provider state changed after preview",
        ):
            adapter.render_payload(update_intent)

        self.assertEqual(
            [call[0] for call in transport.calls],
            ["GET"],
        )

    def test_update_rejects_mismatched_protocol_state(self):
        transport = FakeWriteTransport(github_record())
        adapter = GitHubWriteAdapter(github_target(), transport)

        with self.assertRaisesRegex(
            AdapterError,
            "current status does not match",
        ):
            adapter.render_payload(
                brief_intent(
                    operation=WriteOperation.UPDATE,
                    lifecycle_state="in-progress",
                    previous_lifecycle_state="ready",
                    provider_id="11",
                    expected_provider_state=(
                        "2026-07-30T10:00:00Z"
                    ),
                )
            )

    def test_return_update_rejects_non_pending_provider_item(self):
        record = github_record(
            labels=[
                {"name": "return-kind:evidence-result"},
                {"name": "intake-state:handled"},
            ],
            html_url="https://github.com/owner/docs/issues/11",
        )
        adapter = GitHubWriteAdapter(
            github_intake_store(),
            FakeWriteTransport(record),
        )
        update = WriteIntent(
            operation=WriteOperation.UPDATE,
            target_key="documentation-intake",
            item_kind=ProtocolItemKind.RETURN_ITEM,
            title="Handle evidence",
            body="Evidence body.",
            intake_state=IntakeState.HANDLED,
            previous_intake_state=IntakeState.PENDING,
            return_kind=ReturnKind.EVIDENCE_RESULT,
            relations=(
                TypedRelation(
                    kind=RelationKind.RETURN,
                    target="github:owner/implementation#12",
                ),
            ),
            correlation_id="corr-12",
            provider_id="11",
            expected_provider_state="2026-07-30T10:00:00Z",
        )

        with self.assertRaisesRegex(
            AdapterError,
            "current intake-state does not match",
        ):
            adapter.render_payload(update)

    def test_return_update_coordinator_skips_search_but_guards_pending_state(
        self,
    ):
        record = github_record(
            labels=[
                {"name": "return-kind:evidence-result"},
                {"name": "intake-state:handled"},
            ],
            html_url="https://github.com/owner/docs/issues/11",
        )
        store = github_intake_store()
        transport = FakeWriteTransport(record)
        coordinator = WriteCoordinator(
            WriteTargetConfig(target=store, declarations=()),
            GitHubWriteAdapter(store, transport),
            (),
            preflight_budget=QueryBudget(
                page_size=100,
                max_pages=1,
                max_items=100,
            ),
        )
        update = WriteIntent(
            operation=WriteOperation.UPDATE,
            target_key=store.key,
            item_kind=ProtocolItemKind.RETURN_ITEM,
            title="Handle evidence",
            body="Evidence body.",
            intake_state=IntakeState.HANDLED,
            previous_intake_state=IntakeState.PENDING,
            return_kind=ReturnKind.EVIDENCE_RESULT,
            relations=(
                TypedRelation(
                    kind=RelationKind.RETURN,
                    target="github:owner/implementation#12",
                ),
            ),
            correlation_id="corr-12",
            provider_id="11",
            expected_provider_state="2026-07-30T10:00:00Z",
        )

        with self.assertRaisesRegex(
            AdapterError,
            "current intake-state does not match",
        ):
            coordinator.prepare(
                update,
                CandidateDisposition.CREATE_DISTINCT,
            )

        self.assertEqual(
            [call[0] for call in transport.calls],
            ["GET"],
        )

    def test_update_checks_state_then_patches(self):
        transport = FakeWriteTransport(github_record())
        adapter = GitHubWriteAdapter(github_target(), transport)
        payload = adapter.render_payload(
            brief_intent(
                operation=WriteOperation.UPDATE,
                lifecycle_state="ready",
                previous_lifecycle_state="draft",
                provider_id="11",
                expected_provider_state="2026-07-30T10:00:00Z",
            )
        )

        adapter.update_item(
            "11",
            payload,
            "2026-07-30T10:00:00Z",
        )

        self.assertEqual(
            [call[0] for call in transport.calls],
            ["GET", "GET", "PATCH"],
        )

    def test_normalized_readback_rejects_malformed_protocol_metadata(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )
        record = github_record(
            body=(
                "Body.\n\n"
                "<!-- architecture-handoff-protocol\n"
                "schema-version: 2\n"
            )
        )

        with self.assertRaisesRegex(
            AdapterError,
            "malformed protocol metadata",
        ):
            adapter.normalize_readback(record)

    def test_normalized_readback_rejects_mismatched_logical_target(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )
        payload = adapter.render_payload(brief_intent())
        record = github_record(
            body=payload["body"].replace(
                "logical-target: example-implementation",
                "logical-target: another-target",
            )
        )

        with self.assertRaisesRegex(
            AdapterError,
            "logical target mismatch",
        ):
            adapter.normalize_readback(record)

    def test_normalized_readback_contains_identity_and_comparable_payload(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )

        normalized = adapter.normalize_readback(github_record())

        self.assertEqual(normalized.provider_id, "11")
        self.assertEqual(
            normalized.provider_qualified_id,
            "github:owner/repository#11",
        )
        self.assertEqual(
            json.loads(normalized.comparable_payload_json),
            {
                "body": "One bounded outcome.",
                "labels": [
                    "status:draft",
                    "work-route:architecture-slice-handoff",
                ],
                "title": "Verify deterministic lookup",
            },
        )

    def test_normalized_readback_rejects_duplicate_protocol_labels(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )
        record = github_record(
            labels=[
                {"name": "status:draft"},
                {"name": "status:ready"},
            ]
        )

        with self.assertRaisesRegex(
            AdapterError,
            "multiple status labels",
        ):
            adapter.normalize_readback(record)

    def test_normalized_readback_rejects_wrong_issue_url(self):
        adapter = GitHubWriteAdapter(
            github_target(),
            FakeWriteTransport(github_record()),
        )

        with self.assertRaisesRegex(
            AdapterError,
            "does not match repository and Issue",
        ):
            adapter.normalize_readback(
                github_record(
                    html_url=(
                        "https://example.invalid/"
                        "owner/repository/issues/11"
                    )
                )
            )


if __name__ == "__main__":
    unittest.main()
