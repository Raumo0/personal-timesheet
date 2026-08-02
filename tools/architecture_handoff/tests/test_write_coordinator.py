import json
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.models import (  # noqa: E402
    CapabilityStatus,
    ResultCompleteness,
    WorkRoute,
)
from tools.architecture_handoff.adapter import AdapterBinding  # noqa: E402
from tools.architecture_handoff.github_preflight import (  # noqa: E402
    GitHubQueryCandidateSource,
    advisory_similarity_plan,
)
from tools.architecture_handoff.github import GitHubRateLimitError  # noqa: E402
from tools.architecture_handoff.preflight import (  # noqa: E402
    Candidate,
    CandidateLane,
    PreflightResult,
    PreflightSourceKind,
    SourceApplicability,
    SourceDeclaration,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    LaneRequirement,
    ProviderCall,
    QueryCoverage,
    QueryPurpose,
)
from tools.architecture_handoff.registry import TargetConfig  # noqa: E402
from tools.architecture_handoff.runtime_config import QueryBudget  # noqa: E402
from tools.architecture_handoff.write_coordinator import (  # noqa: E402
    CandidateDisposition,
    NormalizedReadback,
    WriteAuthorization,
    WriteCoordinator,
    WriteTargetConfig,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    ProtocolItemKind,
    RelationKind,
    TypedRelation,
    WriteIntent,
    WriteOperation,
)


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class MutableSource:
    kind = PreflightSourceKind.NATIVE_WORK

    def __init__(self, target):
        self.target = target
        self.candidates = ()
        self.calls = 0
        self.searched_scopes = (
            "github:owner/repository:all-issues",
        )
        self.limitations = ()
        self.results = []
        self.limits = []

    def query(self, _intent, limit):
        self.calls += 1
        self.limits.append(limit)
        result = PreflightResult(
            source_kind=self.kind,
            capability=CapabilityStatus.SUPPORTED,
            completeness=ResultCompleteness.COMPLETE,
            searched_scopes=self.searched_scopes,
            candidates=self.candidates,
            limitations=self.limitations,
        )
        self.results.append(result)
        return result


class MutableQueryCoordinator:
    def __init__(self, coverage, error=None):
        self.coverage = coverage
        self.error = error
        self.binding = AdapterBinding(
            provider="github",
            provider_scope="owner/repository",
            logical_target="example-implementation",
        )
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        if self.error is not None:
            raise self.error
        return replace(self.coverage, plan=plan)


class FakeWriteAdapter:
    def __init__(self, target):
        self.target = target
        self.render_suffix = ""
        self.create_calls = []
        self.update_calls = []
        self.get_calls = []
        self.last_payload = None
        self.mismatch_readback = False

    def render_payload(self, intent):
        return {
            "body": intent.body + self.render_suffix,
            "labels": [
                f"work-route:{intent.route.value}",
                f"status:{intent.lifecycle_state}",
            ],
            "title": intent.title,
        }

    def create_item(self, payload):
        self.create_calls.append(payload)
        self.last_payload = dict(payload)
        return self._record("21")

    def update_item(self, provider_id, payload, expected_state):
        self.update_calls.append((provider_id, payload, expected_state))
        self.last_payload = dict(payload)
        return self._record(provider_id)

    def get_item(self, provider_id):
        self.get_calls.append(provider_id)
        return self._record(provider_id)

    def _record(self, provider_id):
        payload = dict(self.last_payload or {})
        if self.mismatch_readback:
            payload["title"] = "Provider changed the title"
        return {
            "number": int(provider_id),
            "html_url": (
                "https://github.com/owner/repository/issues/"
                f"{provider_id}"
            ),
            "updated_at": "2026-07-30T11:00:00Z",
            "comparable": payload,
        }

    def normalize_readback(self, payload):
        provider_id = str(payload["number"])
        return NormalizedReadback(
            provider="github",
            provider_id=provider_id,
            provider_qualified_id=(
                f"github:owner/repository#{provider_id}"
            ),
            url=str(payload["html_url"]),
            provider_state=str(payload["updated_at"]),
            comparable_payload_json=canonical(payload["comparable"]),
        )


def source_relation():
    return TypedRelation(
        kind=RelationKind.IMPLEMENTATION,
        target="git:owner/docs@abc123:ADR-0003",
        revision="abc123",
    )


def target(**overrides):
    values = {
        "key": "example-implementation",
        "provider": "github",
        "repository": "owner/repository",
        "routing_status": "active",
        "owns": ("pilot implementation",),
        "excludes": (),
    }
    values.update(overrides)
    return TargetConfig(**values)


def intent(**overrides):
    values = {
        "operation": WriteOperation.CREATE,
        "target_key": "example-implementation",
        "item_kind": ProtocolItemKind.WORK_ITEM,
        "title": "Restore accepted conformance",
        "body": "Observed contradiction and expected verification.",
        "route": WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL,
        "lifecycle_state": "draft",
        "relations": (source_relation(),),
    }
    values.update(overrides)
    return WriteIntent(**values)


def declarations():
    return (
        SourceDeclaration(
            kind=PreflightSourceKind.NATIVE_WORK,
            applicability=SourceApplicability.ENABLED,
        ),
        SourceDeclaration(
            kind=PreflightSourceKind.OPENSPEC,
            applicability=SourceApplicability.NOT_APPLICABLE,
            reason="Target has no OpenSpec changes for this pilot state.",
        ),
        SourceDeclaration(
            kind=PreflightSourceKind.DELIVERY,
            applicability=SourceApplicability.NOT_APPLICABLE,
            reason="Target has no delivery records for this pilot state.",
        ),
    )


def existing_candidate():
    return Candidate(
        source_kind=PreflightSourceKind.NATIVE_WORK,
        provider_qualified_id="github:owner/repository#11",
        title="Existing conformance work",
        status="open",
        updated="2026-07-30T10:00:00Z",
        url="https://github.com/owner/repository/issues/11",
    )


def similarity_intent():
    return intent(
        capability="account-address-prediction",
        expected_outcome="Return one deterministic address",
    )


def similarity_coverage(*, scopes=("github:owner/repository:issue-search",),
                        limitations=()):
    plan = advisory_similarity_plan(similarity_intent(), 100)
    return QueryCoverage(
        plan=plan,
        capability=CapabilityStatus.SUPPORTED,
        completeness=(
            ResultCompleteness.PARTIAL
            if limitations
            else ResultCompleteness.COMPLETE
        ),
        hits=(),
        calls=(
            ProviderCall(
                purpose=QueryPurpose.SIMILARITY,
                cursor=None,
                searched_scopes=scopes,
            ),
        ),
        limitations=limitations,
    )


class WriteCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.target = target()
        self.source = MutableSource(self.target)
        self.adapter = FakeWriteAdapter(self.target)
        self.coordinator = WriteCoordinator(
            WriteTargetConfig(
                target=self.target,
                declarations=declarations(),
            ),
            self.adapter,
            (self.source,),
            preflight_budget=QueryBudget(
                page_size=40,
                max_pages=1,
                max_items=80,
            ),
        )

    def prepare(self, **kwargs):
        return self.coordinator.prepare(
            kwargs.pop("intent", intent()),
            kwargs.pop(
                "disposition",
                CandidateDisposition.CREATE_DISTINCT,
            ),
            **kwargs,
        )

    def authorize(self, prepared, reference="session-approval-1"):
        return WriteAuthorization(
            fingerprint=prepared.fingerprint,
            approval_reference=reference,
        )

    def coordinator_with_similarity_lane(self, coverage=None, error=None):
        query_coordinator = MutableQueryCoordinator(
            coverage or similarity_coverage(),
            error=error,
        )
        similarity_source = GitHubQueryCandidateSource(
            self.target,
            query_coordinator,
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )
        coordinator = WriteCoordinator(
            WriteTargetConfig(
                target=self.target,
                declarations=declarations(),
            ),
            self.adapter,
            (self.source,),
            candidate_lanes=(
                CandidateLane(
                    name="semantic-candidates",
                    requirement=LaneRequirement.ADVISORY,
                    source=similarity_source,
                ),
            ),
            preflight_budget=QueryBudget(
                page_size=40,
                max_pages=1,
                max_items=80,
            ),
        )
        return coordinator, query_coordinator

    def test_execute_reruns_same_bound_advisory_lane(self):
        coordinator, query_coordinator = (
            self.coordinator_with_similarity_lane()
        )
        prepared = coordinator.prepare(
            similarity_intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )

        coordinator.execute(prepared, self.authorize(prepared))

        self.assertEqual(
            prepared.preflight.advisory_results,
            (
                prepared.preflight.candidate_lanes[0].result,
            ),
        )
        self.assertEqual(len(query_coordinator.plans), 2)
        self.assertEqual(
            query_coordinator.plans[0],
            query_coordinator.plans[1],
        )

    def test_signal_free_similarity_is_visible_and_does_not_block_prepare(self):
        coordinator, query_coordinator = (
            self.coordinator_with_similarity_lane()
        )

        prepared = coordinator.prepare(
            intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )

        advisory = prepared.preflight.advisory_results[0]
        self.assertIs(advisory.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(advisory.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertIsNone(advisory.plan)
        self.assertTrue(advisory.limitations[0])
        self.assertTrue(prepared.fingerprint)
        self.assertEqual(query_coordinator.plans, [])

    def test_zero_call_interruption_is_advisory_and_fingerprinted(self):
        coordinator, query_coordinator = (
            self.coordinator_with_similarity_lane(
                error=GitHubRateLimitError("30"),
            )
        )
        prepared = coordinator.prepare(
            similarity_intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )

        advisory = prepared.preflight.advisory_results[0]
        self.assertIs(advisory.capability, CapabilityStatus.PARTIAL)
        self.assertIs(advisory.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(advisory.calls, ())
        self.assertEqual(advisory.candidates, ())
        self.assertTrue(advisory.limitations)
        self.assertTrue(prepared.fingerprint)

        query_coordinator.error = GitHubRateLimitError("60")
        with self.assertRaisesRegex(ValueError, "prepared write is stale"):
            coordinator.execute(prepared, self.authorize(prepared))

    def test_changed_query_coverage_invalidates_authorization(self):
        coordinator, query_coordinator = (
            self.coordinator_with_similarity_lane()
        )
        prepared = coordinator.prepare(
            similarity_intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )
        query_coordinator.coverage = similarity_coverage(
            scopes=("github:owner/repository:changed-scope",),
        )

        with self.assertRaisesRegex(ValueError, "prepared write is stale"):
            coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_changed_returned_cursor_invalidates_authorization(self):
        coordinator, query_coordinator = (
            self.coordinator_with_similarity_lane(
                replace(
                    similarity_coverage(
                        limitations=(
                            "additional provider page is available",
                        )
                    ),
                    next_cursor="2",
                )
            )
        )
        prepared = coordinator.prepare(
            similarity_intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )
        query_coordinator.coverage = replace(
            similarity_coverage(
                limitations=(
                    "additional provider page is available",
                )
            ),
            next_cursor="999",
        )

        with self.assertRaisesRegex(ValueError, "prepared write is stale"):
            coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_changed_advisory_limitation_invalidates_authorization(self):
        coordinator, query_coordinator = (
            self.coordinator_with_similarity_lane(
                similarity_coverage(
                    limitations=("provider search is rate limited",),
                )
            )
        )
        prepared = coordinator.prepare(
            similarity_intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )
        query_coordinator.coverage = similarity_coverage(
            limitations=("provider search remains rate limited",),
        )

        with self.assertRaisesRegex(ValueError, "prepared write is stale"):
            coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

    def test_prepare_performs_no_write(self):
        prepared = self.prepare()

        self.assertEqual(self.adapter.create_calls, [])
        self.assertEqual(self.adapter.update_calls, [])
        self.assertEqual(self.source.calls, 1)
        self.assertEqual(self.source.limits, [40])
        self.assertIsInstance(prepared.provider_payload_json, str)

    def test_coordinator_binds_exact_active_target_and_adapter(self):
        wrong_target = target(repository="owner/other")

        with self.assertRaisesRegex(
            ValueError,
            "adapter target does not match",
        ):
            WriteCoordinator(
                WriteTargetConfig(
                    target=self.target,
                    declarations=declarations(),
                ),
                FakeWriteAdapter(wrong_target),
                (self.source,),
                preflight_budget=QueryBudget(
                    page_size=40,
                    max_pages=1,
                    max_items=80,
                ),
            )

        with self.assertRaisesRegex(
            ValueError,
            "intent target does not match",
        ):
            self.prepare(
                intent=intent(target_key="another-target")
            )

    def test_not_applicable_source_cannot_hide_bound_adapter(self):
        openspec_source = MutableSource(self.target)
        openspec_source.kind = PreflightSourceKind.OPENSPEC

        with self.assertRaisesRegex(
            ValueError,
            "not-applicable source must not have an adapter",
        ):
            WriteCoordinator(
                WriteTargetConfig(
                    target=self.target,
                    declarations=declarations(),
                ),
                self.adapter,
                (self.source, openspec_source),
                preflight_budget=QueryBudget(
                    page_size=40,
                    max_pages=1,
                    max_items=80,
                ),
            )

    def test_create_distinct_with_candidates_requires_reason(self):
        self.source.candidates = (existing_candidate(),)

        with self.assertRaisesRegex(
            ValueError,
            "create-distinct requires a reason",
        ):
            self.prepare()

        prepared = self.prepare(
            disposition_reason="The expected outcome is different.",
        )
        self.assertEqual(
            prepared.disposition_reason,
            "The expected outcome is different.",
        )

    def test_link_and_supersede_require_related_candidate_identity(self):
        self.source.candidates = (existing_candidate(),)

        for disposition in (
            CandidateDisposition.LINK_AND_NARROW,
            CandidateDisposition.SUPERSEDE,
        ):
            with self.subTest(disposition=disposition):
                with self.assertRaisesRegex(
                    ValueError,
                    "requires a related candidate identity",
                ):
                    self.prepare(disposition=disposition)

    def test_execute_requires_non_empty_approval_reference(self):
        prepared = self.prepare()

        with self.assertRaisesRegex(
            ValueError,
            "approval_reference",
        ):
            self.coordinator.execute(
                prepared,
                self.authorize(prepared, reference=" "),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_authorization_must_match_exact_fingerprint(self):
        prepared = self.prepare()

        with self.assertRaisesRegex(
            ValueError,
            "authorization fingerprint",
        ):
            self.coordinator.execute(
                prepared,
                WriteAuthorization(
                    fingerprint="0" * 64,
                    approval_reference="session-approval-1",
                ),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_changed_candidate_set_invalidates_authorization(self):
        prepared = self.prepare()
        self.source.candidates = (existing_candidate(),)

        with self.assertRaisesRegex(
            ValueError,
            "prepared write is stale",
        ):
            self.coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_changed_rendered_payload_invalidates_authorization(self):
        prepared = self.prepare()
        self.adapter.render_suffix = "\nChanged after preview."

        with self.assertRaisesRegex(
            ValueError,
            "prepared write is stale",
        ):
            self.coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_prepared_payload_cannot_be_mutated(self):
        prepared = self.prepare()
        decoded = json.loads(prepared.provider_payload_json)
        decoded["title"] = "Changed outside prepared write"

        self.assertNotEqual(
            canonical(decoded),
            prepared.provider_payload_json,
        )
        self.assertEqual(
            json.loads(prepared.provider_payload_json)["title"],
            intent().title,
        )

    def test_reuse_disposition_cannot_create_new_item(self):
        self.source.candidates = (existing_candidate(),)
        prepared = self.prepare(
            disposition=CandidateDisposition.REUSE_OR_REOPEN,
        )

        with self.assertRaisesRegex(
            ValueError,
            "reuse-or-reopen does not create a new item",
        ):
            self.coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

        self.assertEqual(self.adapter.create_calls, [])

    def test_create_requires_readback_match(self):
        prepared = self.prepare()

        receipt = self.coordinator.execute(
            prepared,
            self.authorize(prepared),
        )

        self.assertEqual(len(self.adapter.create_calls), 1)
        self.assertEqual(self.adapter.get_calls, ["21"])
        self.assertEqual(receipt.provider_id, "21")
        self.assertEqual(
            receipt.provider_qualified_id,
            "github:owner/repository#21",
        )
        self.assertEqual(
            receipt.url,
            "https://github.com/owner/repository/issues/21",
        )
        self.assertEqual(receipt.provider, "github")
        self.assertEqual(
            receipt.route,
            WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL,
        )
        self.assertEqual(receipt.lifecycle_state, "draft")
        self.assertEqual(receipt.relations, (source_relation(),))
        self.assertIs(receipt.preflight.results[0], self.source.results[-1])
        self.assertIsNot(
            receipt.preflight.results[0],
            prepared.preflight.results[0],
        )
        with self.assertRaises(FrozenInstanceError):
            receipt.preflight.results = ()

    def test_update_requires_readback_match(self):
        update_intent = intent(
            operation=WriteOperation.UPDATE,
            provider_id="11",
            expected_provider_state="2026-07-30T10:00:00Z",
        )
        prepared = self.prepare(intent=update_intent)

        receipt = self.coordinator.execute(
            prepared,
            self.authorize(prepared),
        )

        self.assertEqual(
            self.adapter.update_calls[0][0],
            "11",
        )
        self.assertEqual(
            self.adapter.update_calls[0][2],
            "2026-07-30T10:00:00Z",
        )
        self.assertEqual(self.adapter.get_calls, ["11"])
        self.assertEqual(receipt.operation, WriteOperation.UPDATE)
        self.assertIs(receipt.preflight.results[0], self.source.results[-1])
        self.assertIsNot(
            receipt.preflight.results[0],
            prepared.preflight.results[0],
        )

    def test_receipt_preserves_full_rerun_query_lane_evidence(self):
        coordinator, _query_coordinator = (
            self.coordinator_with_similarity_lane()
        )
        prepared = coordinator.prepare(
            similarity_intent(),
            CandidateDisposition.CREATE_DISTINCT,
        )

        receipt = coordinator.execute(
            prepared,
            self.authorize(prepared),
        )

        lane = receipt.preflight.candidate_lanes[0]
        self.assertEqual(lane.name, "semantic-candidates")
        self.assertIs(lane.requirement, LaneRequirement.ADVISORY)
        self.assertIsNotNone(lane.result.plan)
        self.assertTrue(lane.result.calls)
        self.assertEqual(
            lane.result.searched_scopes,
            tuple(
                scope
                for call in lane.result.calls
                for scope in call.searched_scopes
            ),
        )
        self.assertIs(lane.result.capability, CapabilityStatus.SUPPORTED)
        self.assertIs(
            lane.result.completeness,
            ResultCompleteness.COMPLETE,
        )

    def test_changed_exact_evidence_blocks_update_before_provider_write(self):
        update_intent = intent(
            operation=WriteOperation.UPDATE,
            provider_id="11",
            expected_provider_state="2026-07-30T10:00:00Z",
        )
        prepared = self.prepare(intent=update_intent)
        self.source.searched_scopes = (
            "github:owner/repository:changed-scope",
        )

        with self.assertRaisesRegex(ValueError, "prepared write is stale"):
            self.coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

        self.assertEqual(self.adapter.update_calls, [])

    def test_readback_mismatch_fails_without_receipt(self):
        prepared = self.prepare()
        self.adapter.mismatch_readback = True

        with self.assertRaisesRegex(
            ValueError,
            "readback payload mismatch",
        ):
            self.coordinator.execute(
                prepared,
                self.authorize(prepared),
            )

    def test_authorized_write_cannot_be_replayed(self):
        prepared = self.prepare()
        authorization = self.authorize(prepared)
        self.coordinator.execute(
            prepared,
            authorization,
        )

        with self.assertRaisesRegex(
            ValueError,
            "already attempted",
        ):
            self.coordinator.execute(
                prepared,
                authorization,
            )

        self.assertEqual(len(self.adapter.create_calls), 1)


if __name__ == "__main__":
    unittest.main()
