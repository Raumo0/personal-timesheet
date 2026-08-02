import json
import re
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.github import (  # noqa: E402
    AdapterError,
)
from tools.architecture_handoff.protocol_metadata import (  # noqa: E402
    ALL_PROTOCOL_LABELS,
)
from tools.architecture_handoff.provisioning import (  # noqa: E402
    ProvisioningAdapterCallError,
    ProvisioningError,
)
from tools.architecture_handoff.provisioning_models import (  # noqa: E402
    ProvisioningAction,
    ProvisioningActionReceipt,
    ProvisioningCall,
    ProvisioningRequirement,
    ProvisioningResourceState,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    StoreConfig,
    StoreRole,
)

try:
    from tools.architecture_handoff.github import (  # noqa: E402
        GitHubNotFoundError,
    )
except ImportError:
    GitHubNotFoundError = None

try:
    from tools.architecture_handoff.github_provisioning import (  # noqa: E402
        GITHUB_PROTOCOL_LABEL_MANIFEST,
        GitHubProvisioningAdapter,
    )
except ImportError:
    GITHUB_PROTOCOL_LABEL_MANIFEST = None
    GitHubProvisioningAdapter = None


EXPECTED_MANIFEST = {
    "work-route:architecture-slice-handoff": {
        "color": "1D76DB",
        "description": "Implements one bounded architecture slice",
    },
    "work-route:implementation-conformance-referral": {
        "color": "D93F0B",
        "description": "Corrects implementation against accepted sources",
    },
    "work-route:spike-evidence": {
        "color": "5319E7",
        "description": "Returns bounded evidence before dependent work",
    },
    "status:draft": {
        "color": "C5DEF5",
        "description": "Created but not ready for execution",
    },
    "status:backlog": {
        "color": "D4C5F9",
        "description": "Deferred and retained for later selection",
    },
    "status:ready": {
        "color": "0E8A16",
        "description": "Authorized and ready for execution",
    },
    "status:in-progress": {
        "color": "FBCA04",
        "description": "Execution is in progress",
    },
    "status:in-review": {
        "color": "0052CC",
        "description": "Awaiting required review",
    },
    "status:done": {
        "color": "006B75",
        "description": "Required work and verification completed",
    },
    "status:cancelled": {
        "color": "B60205",
        "description": "Work was cancelled without completion",
    },
    "return-kind:evidence-result": {
        "color": "1D76DB",
        "description": "Returned evidence for validation and routing",
    },
    "return-kind:product-gap": {
        "color": "D93F0B",
        "description": "Product clarification or decision required",
    },
    "return-kind:architecture-gap": {
        "color": "5319E7",
        "description": "Architecture clarification or decision required",
    },
    "intake-state:pending": {
        "color": "FBCA04",
        "description": "Awaiting documentation-side handling",
    },
    "intake-state:handled": {
        "color": "0E8A16",
        "description": "Documentation-side follow-up completed or linked",
    },
}


def github_intake_store():
    return StoreConfig(
        key="documentation-intake",
        role=StoreRole.DOCUMENTATION_INTAKE,
        provider="github",
        repository="owner/docs",
        routing_status="active",
        tracker_reference="github:owner/docs",
    )


def requirement(name="intake-state:pending"):
    return ProvisioningRequirement(
        family=name.split(":", 1)[0],
        name=name,
    )


class FakeProvisioningTransport:
    def __init__(self):
        self.get_result = None
        self.post_result = None
        self.calls = []

    def get(self, path, params):
        self.calls.append(("GET", path, params))
        if isinstance(self.get_result, Exception):
            raise self.get_result
        return self.get_result, None

    def post(self, path, payload):
        self.calls.append(("POST", path, payload))
        if isinstance(self.post_result, Exception):
            raise self.post_result
        return self.post_result, None


class GitHubProtocolLabelManifestTests(unittest.TestCase):
    def test_manifest_exactly_covers_protocol_labels_with_approved_defaults(self):
        self.assertIsNotNone(
            GITHUB_PROTOCOL_LABEL_MANIFEST,
            "GITHUB_PROTOCOL_LABEL_MANIFEST does not exist",
        )
        self.assertEqual(
            set(GITHUB_PROTOCOL_LABEL_MANIFEST),
            set(ALL_PROTOCOL_LABELS),
        )
        self.assertEqual(
            dict(GITHUB_PROTOCOL_LABEL_MANIFEST),
            EXPECTED_MANIFEST,
        )

    def test_manifest_presentation_is_valid_and_token_safe(self):
        self.assertIsNotNone(
            GITHUB_PROTOCOL_LABEL_MANIFEST,
            "GITHUB_PROTOCOL_LABEL_MANIFEST does not exist",
        )
        unsafe_terms = (
            "credential",
            "password",
            "secret",
            "token",
            "/users/",
            "\\users\\",
        )
        for name, presentation in GITHUB_PROTOCOL_LABEL_MANIFEST.items():
            with self.subTest(name=name):
                self.assertRegex(
                    presentation["color"],
                    re.compile(r"\A[0-9A-Fa-f]{6}\Z"),
                )
                description = presentation["description"]
                self.assertTrue(description)
                normalized = description.lower()
                self.assertFalse(
                    any(term in normalized for term in unsafe_terms)
                )


class GitHubProvisioningAdapterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            GitHubProvisioningAdapter,
            "GitHubProvisioningAdapter does not exist",
        )
        self.transport = FakeProvisioningTransport()
        self.adapter = GitHubProvisioningAdapter(
            github_intake_store(),
            self.transport,
            create_enabled=True,
        )

    def test_exact_label_inspection_uses_one_encoded_endpoint_and_maps_missing(self):
        self.assertIsNotNone(
            GitHubNotFoundError,
            "GitHubNotFoundError does not exist",
        )
        self.transport.get_result = GitHubNotFoundError()

        observation, calls = self.adapter.inspect(
            requirement("return-kind:evidence-result")
        )

        self.assertIs(
            observation.state,
            ProvisioningResourceState.MISSING,
        )
        self.assertEqual(
            self.transport.calls,
            [
                (
                    "GET",
                    (
                        "repos/owner/docs/labels/"
                        "return-kind%3Aevidence-result"
                    ),
                    {},
                )
            ],
        )
        self.assertEqual(
            calls,
            (
                ProvisioningCall(
                    operation="inspect",
                    resource_type="label",
                    stable_id="return-kind:evidence-result",
                ),
            ),
        )

    def test_exact_matching_label_is_satisfied(self):
        self.transport.get_result = {
            "name": "intake-state:pending",
            "color": "fbca04",
            "description": "Awaiting documentation-side handling",
        }

        observation, calls = self.adapter.inspect(requirement())

        self.assertIs(
            observation.state,
            ProvisioningResourceState.SATISFIED,
        )
        self.assertEqual(
            observation.observed_presentation_json,
            observation.resource.presentation_json,
        )
        self.assertEqual(len(calls), 1)

    def test_presentation_difference_is_style_drift(self):
        self.transport.get_result = {
            "name": "intake-state:pending",
            "color": "FFFFFF",
            "description": "Existing custom presentation",
        }

        observation, _ = self.adapter.inspect(requirement())

        self.assertIs(
            observation.state,
            ProvisioningResourceState.STYLE_DRIFT,
        )
        self.assertEqual(
            json.loads(observation.observed_presentation_json),
            {
                "color": "FFFFFF",
                "description": "Existing custom presentation",
            },
        )

    def test_null_description_is_style_drift_not_malformed(self):
        self.transport.get_result = {
            "name": "intake-state:pending",
            "color": "FBCA04",
            "description": None,
        }

        observation, _ = self.adapter.inspect(requirement())

        self.assertIs(
            observation.state,
            ProvisioningResourceState.STYLE_DRIFT,
        )
        self.assertEqual(
            json.loads(observation.observed_presentation_json),
            {
                "color": "FBCA04",
                "description": None,
            },
        )

    def test_case_or_name_conflict_preserves_only_safe_observed_metadata(self):
        cases = (
            {
                "name": "Intake-State:Pending",
                "color": "FBCA04",
                "description": "Awaiting documentation-side handling",
                "raw_secret": "must-not-be-preserved",
            },
            {
                "name": "intake-state:handled",
                "color": "FBCA04",
                "description": "Awaiting documentation-side handling",
            },
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.transport.get_result = payload

                observation, calls = self.adapter.inspect(requirement())

                self.assertIs(
                    observation.state,
                    ProvisioningResourceState.CONFLICTING,
                )
                self.assertEqual(
                    observation.observed_identity,
                    payload["name"],
                )
                self.assertEqual(
                    json.loads(observation.observed_presentation_json),
                    {
                        "color": "FBCA04",
                        "description": (
                            "Awaiting documentation-side handling"
                        ),
                    },
                )
                self.assertNotIn(
                    "raw_secret",
                    repr(observation),
                )
                self.assertTrue(observation.limitation)
                self.assertEqual(len(calls), 1)

    def test_malformed_payload_is_conflicting_without_raw_body(self):
        cases = (
            {
                "name": "intake-state:pending",
                "color": "not-a-color",
                "description": "Awaiting documentation-side handling",
            },
            ["malformed"],
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.transport.get_result = payload

                observation, calls = self.adapter.inspect(requirement())

                self.assertIs(
                    observation.state,
                    ProvisioningResourceState.CONFLICTING,
                )
                self.assertTrue(observation.limitation)
                self.assertEqual(len(calls), 1)

    def test_only_typed_not_found_is_missing_and_other_failures_keep_call(self):
        self.transport.get_result = AdapterError("permission denied")

        with self.assertRaisesRegex(
            ProvisioningAdapterCallError,
            "permission denied",
        ) as raised:
            self.adapter.inspect(requirement())
        self.assertEqual(
            raised.exception.provider_calls,
            (
                ProvisioningCall(
                    operation="inspect",
                    resource_type="label",
                    stable_id="intake-state:pending",
                ),
            ),
        )

    def test_create_posts_only_manifest_payload_and_returns_one_receipt(self):
        self.transport.get_result = GitHubNotFoundError()
        missing, _ = self.adapter.inspect(requirement())
        action = ProvisioningAction(
            requirement=missing.requirement,
            resource=missing.resource,
        )
        self.transport.calls.clear()
        self.transport.post_result = {
            "id": 123,
            "name": "intake-state:pending",
            "color": "fbca04",
            "description": "Awaiting documentation-side handling",
        }

        receipt, calls = self.adapter.create(action)

        self.assertEqual(
            receipt,
            ProvisioningActionReceipt(action=action, calls=calls),
        )
        self.assertEqual(
            self.transport.calls,
            [
                (
                    "POST",
                    "repos/owner/docs/labels",
                    {
                        "name": "intake-state:pending",
                        "color": "FBCA04",
                        "description": (
                            "Awaiting documentation-side handling"
                        ),
                    },
                )
            ],
        )
        self.assertEqual(
            calls,
            (
                ProvisioningCall(
                    operation="create",
                    resource_type="label",
                    stable_id="intake-state:pending",
                ),
            ),
        )

    def test_create_is_blocked_at_adapter_boundary_without_credentials(self):
        self.transport.get_result = GitHubNotFoundError()
        missing, _ = self.adapter.inspect(requirement())
        action = ProvisioningAction(
            requirement=missing.requirement,
            resource=missing.resource,
        )
        blocked = GitHubProvisioningAdapter(
            github_intake_store(),
            self.transport,
            create_enabled=False,
        )
        self.transport.calls.clear()

        with self.assertRaisesRegex(ProvisioningError, "GITHUB_TOKEN"):
            blocked.create(action)

        self.assertEqual(self.transport.calls, [])

    def test_create_rejects_wrong_action_or_returned_identity(self):
        self.transport.get_result = GitHubNotFoundError()
        missing, _ = self.adapter.inspect(requirement())
        action = ProvisioningAction(
            requirement=missing.requirement,
            resource=missing.resource,
        )
        cases = (
            {
                "name": "Intake-State:Pending",
                "color": "FBCA04",
                "description": "Awaiting documentation-side handling",
            },
            {
                "name": "intake-state:pending",
                "color": "FFFFFF",
                "description": "Awaiting documentation-side handling",
            },
            {"name": "intake-state:pending"},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.transport.post_result = payload
                with self.assertRaisesRegex(
                    ProvisioningAdapterCallError,
                    "GitHub label creation response",
                ):
                    self.adapter.create(action)

        wrong_resource = type(action.resource)(
            resource_type="label",
            stable_id=action.stable_id,
            create_payload_json=json.dumps(
                {
                    "color": "FFFFFF",
                    "description": "Unapproved",
                    "name": action.stable_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            presentation_json=json.dumps(
                {
                    "color": "FFFFFF",
                    "description": "Unapproved",
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        wrong_action = ProvisioningAction(
            requirement=action.requirement,
            resource=wrong_resource,
        )
        self.transport.calls.clear()
        with self.assertRaisesRegex(
            AdapterError,
            "does not match the GitHub label manifest",
        ):
            self.adapter.create(wrong_action)
        self.assertEqual(self.transport.calls, [])

    def test_create_failure_preserves_attempted_provider_call(self):
        self.transport.get_result = GitHubNotFoundError()
        missing, _ = self.adapter.inspect(requirement())
        action = ProvisioningAction(
            requirement=missing.requirement,
            resource=missing.resource,
        )
        self.transport.post_result = AdapterError("permission denied")

        with self.assertRaisesRegex(
            ProvisioningAdapterCallError,
            "permission denied",
        ) as raised:
            self.adapter.create(action)

        self.assertEqual(
            raised.exception.provider_calls,
            (
                ProvisioningCall(
                    operation="create",
                    resource_type="label",
                    stable_id="intake-state:pending",
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
