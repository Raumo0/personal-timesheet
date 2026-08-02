import hashlib
import sys
import unittest
from itertools import count
from pathlib import Path
from threading import Event, Thread


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.provisioning import (  # noqa: E402
    ProvisioningAdapterCallError,
    ProvisioningCoordinator,
    ProvisioningError,
    ProvisioningExecutionError,
)
from tools.architecture_handoff.provisioning_attempts import (  # noqa: E402
    InMemoryProvisioningAttemptStore,
)
from tools.architecture_handoff.provisioning_models import (  # noqa: E402
    ProvisioningActionReceipt,
    ProvisioningAuthorization,
    ProvisioningCall,
    ProvisioningObservation,
    ProvisioningResourceSpec,
    ProvisioningResourceState,
    requirements_for_endpoint,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    StoreConfig,
    StoreRole,
)
from tools.architecture_handoff.write_coordinator import (  # noqa: E402
    canonical_json,
)


def store(**overrides):
    values = {
        "key": "documentation-intake",
        "role": StoreRole.DOCUMENTATION_INTAKE,
        "provider": "github",
        "repository": "owner/docs",
        "routing_status": "active",
    }
    values.update(overrides)
    return StoreConfig(**values)


def resource(requirement, *, payload_suffix=""):
    color = "FBCA04" if not payload_suffix else payload_suffix
    return ProvisioningResourceSpec(
        resource_type="label",
        stable_id=requirement.name,
        create_payload_json=canonical_json(
            {
                "color": color,
                "description": f"Protocol classifier {requirement.name}",
                "name": requirement.name,
            }
        ),
        presentation_json=canonical_json(
            {
                "color": color,
                "description": f"Protocol classifier {requirement.name}",
            }
        ),
    )


class FakeProvisioningAdapter:
    def __init__(
        self,
        endpoint,
        *,
        states=None,
        payload_suffixes=None,
        inspect_operation="inspect",
    ):
        self.endpoint = endpoint
        self.states = dict(states or {})
        self.payload_suffixes = dict(payload_suffixes or {})
        self.inspect_operation = inspect_operation
        self.create_calls = []
        self.inspect_calls = []
        self.fail_on = None
        self.fail_inspect_at = None
        self.leave_missing = set()
        self.first_create_entered = None
        self.release_first_create = None
        self.attempt_store = InMemoryProvisioningAttemptStore()
        self.preparation_ids = PreparationIds()

    def ensure_create_available(self, actions):
        return None

    def inspect(self, requirement):
        self.inspect_calls.append(requirement.name)
        call = ProvisioningCall(
            operation=self.inspect_operation,
            resource_type="label",
            stable_id=requirement.name,
        )
        if len(self.inspect_calls) == self.fail_inspect_at:
            raise ProvisioningAdapterCallError(
                f"provider rejected inspection for {requirement.name}",
                provider_calls=(call,),
            )
        state = self.states.get(
            requirement.name,
            ProvisioningResourceState.SATISFIED,
        )
        specification = resource(
            requirement,
            payload_suffix=self.payload_suffixes.get(requirement.name, ""),
        )
        values = {
            "requirement": requirement,
            "resource": specification,
            "state": state,
        }
        if state is ProvisioningResourceState.SATISFIED:
            values["observed_presentation_json"] = (
                specification.presentation_json
            )
        elif state is ProvisioningResourceState.STYLE_DRIFT:
            values["observed_presentation_json"] = '{"color":"ffffff"}'
        elif state is ProvisioningResourceState.CONFLICTING:
            values["limitation"] = (
                f"provider has an incompatible {requirement.name} resource"
            )
        observation = ProvisioningObservation(**values)
        return observation, (call,)

    def create(self, action):
        self.create_calls.append(action.stable_id)
        call = ProvisioningCall(
            operation="create",
            resource_type=action.resource.resource_type,
            stable_id=action.stable_id,
        )
        if (
            len(self.create_calls) == 1
            and self.first_create_entered is not None
            and self.release_first_create is not None
        ):
            self.first_create_entered.set()
            if not self.release_first_create.wait(timeout=5):
                raise RuntimeError("test timed out waiting to release create")
        if action.stable_id == self.fail_on:
            raise ProvisioningAdapterCallError(
                f"provider rejected {action.stable_id}",
                provider_calls=(call,),
            )
        if action.stable_id not in self.leave_missing:
            self.states[action.stable_id] = ProvisioningResourceState.SATISFIED
        receipt = ProvisioningActionReceipt(action=action, calls=(call,))
        return receipt, (call,)


class PreparationIds:
    def __init__(self):
        self._ids = count(1)

    def __call__(self):
        return f"prep_{next(self._ids):043d}"


_endpoint_ids = count(1)


def coordinator_with_states(states):
    endpoint = store(repository=f"owner/docs-{next(_endpoint_ids)}")
    adapter = FakeProvisioningAdapter(endpoint, states=states)
    coordinator = ProvisioningCoordinator(
        endpoint,
        adapter,
        attempt_store=adapter.attempt_store,
        preparation_id_factory=adapter.preparation_ids,
    )
    return coordinator, adapter


class ProvisioningCoordinatorTests(unittest.TestCase):
    missing_id = "return-kind:evidence-result"
    second_missing_id = "intake-state:pending"

    def authorization(self, prepared, reference="human-gate-1"):
        return ProvisioningAuthorization(
            fingerprint=prepared.fingerprint,
            preparation_id=prepared.preparation_id,
            approval_reference=reference,
        )

    def test_check_is_read_only_and_records_every_inspection_call(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.MISSING}
        )

        check = coordinator.check()

        self.assertEqual(adapter.create_calls, [])
        self.assertEqual(
            adapter.inspect_calls,
            [requirement.name for requirement in check.requirements],
        )
        self.assertEqual(
            tuple(call.stable_id for call in check.calls),
            tuple(requirement.name for requirement in check.requirements),
        )

    def test_prepare_contains_only_missing_actions_and_keeps_style_drift_advisory(self):
        coordinator, adapter = coordinator_with_states(
            {
                self.missing_id: ProvisioningResourceState.MISSING,
                self.second_missing_id: ProvisioningResourceState.STYLE_DRIFT,
            }
        )

        prepared = coordinator.prepare()

        self.assertEqual(
            tuple(action.stable_id for action in prepared.actions),
            (self.missing_id,),
        )
        self.assertEqual(adapter.create_calls, [])
        self.assertTrue(
            any(
                self.second_missing_id in limitation
                for limitation in prepared.check.limitations
            )
        )

    def test_conflicting_observation_blocks_preparation(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.CONFLICTING}
        )

        with self.assertRaisesRegex(ProvisioningError, "conflicting"):
            coordinator.prepare()

        self.assertEqual(adapter.create_calls, [])

    def test_fingerprint_is_sha256_of_complete_canonical_preparation(self):
        coordinator, _adapter = coordinator_with_states(
            {
                self.missing_id: ProvisioningResourceState.MISSING,
                self.second_missing_id: ProvisioningResourceState.STYLE_DRIFT,
            }
        )

        prepared = coordinator.prepare()
        material = canonical_json(
            {
                "endpoint": prepared.check.endpoint,
                "requirements": prepared.check.requirements,
                "check": prepared.check,
                "actions": prepared.actions,
            }
        )

        self.assertEqual(
            prepared.fingerprint,
            hashlib.sha256(material.encode("utf-8")).hexdigest(),
        )

    def test_fingerprint_changes_with_calls_and_exact_action_payload(self):
        endpoint = store()
        baseline_adapter = FakeProvisioningAdapter(
            endpoint,
            states={self.missing_id: ProvisioningResourceState.MISSING},
        )
        changed_call_adapter = FakeProvisioningAdapter(
            endpoint,
            states={self.missing_id: ProvisioningResourceState.MISSING},
            inspect_operation="read-labels",
        )
        changed_payload_adapter = FakeProvisioningAdapter(
            endpoint,
            states={self.missing_id: ProvisioningResourceState.MISSING},
            payload_suffixes={self.missing_id: "0E8A16"},
        )

        baseline = ProvisioningCoordinator(
            endpoint, baseline_adapter
        ).prepare()
        changed_call = ProvisioningCoordinator(
            endpoint, changed_call_adapter
        ).prepare()
        changed_payload = ProvisioningCoordinator(
            endpoint, changed_payload_adapter
        ).prepare()

        self.assertNotEqual(baseline.fingerprint, changed_call.fingerprint)
        self.assertNotEqual(baseline.fingerprint, changed_payload.fingerprint)

    def test_execute_rejects_changed_observation_before_create(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.MISSING}
        )
        prepared = coordinator.prepare()
        adapter.states[self.missing_id] = ProvisioningResourceState.SATISFIED

        with self.assertRaisesRegex(
            ProvisioningError,
            "fingerprint changed",
        ):
            coordinator.execute(self.authorization(prepared))

        self.assertEqual(adapter.create_calls, [])

    def test_execute_rejects_blank_approval_reference_before_create(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.MISSING}
        )
        prepared = coordinator.prepare()
        authorization = self.authorization(prepared)
        object.__setattr__(authorization, "approval_reference", " ")

        with self.assertRaisesRegex(ProvisioningError, "approval_reference"):
            coordinator.execute(authorization)

        self.assertEqual(adapter.create_calls, [])

    def test_execute_attempts_every_approved_missing_resource_once(self):
        coordinator, adapter = coordinator_with_states(
            {
                self.missing_id: ProvisioningResourceState.MISSING,
                self.second_missing_id: ProvisioningResourceState.MISSING,
            }
        )
        prepared = coordinator.prepare()

        receipt = coordinator.execute(self.authorization(prepared))

        self.assertEqual(
            adapter.create_calls,
            [self.missing_id, self.second_missing_id],
        )
        self.assertEqual(
            tuple(item.stable_id for item in receipt.action_receipts),
            (self.missing_id, self.second_missing_id),
        )
        self.assertTrue(
            all(
                observation.state
                is not ProvisioningResourceState.MISSING
                for observation in receipt.readback.observations
            )
        )
        expected_ids = tuple(
            requirement.name for requirement in prepared.check.requirements
        )
        self.assertEqual(
            tuple(
                (call.operation, call.stable_id)
                for call in receipt.calls
            ),
            (
                *(("inspect", stable_id) for stable_id in expected_ids),
                ("create", self.missing_id),
                ("create", self.second_missing_id),
                *(("inspect", stable_id) for stable_id in expected_ids),
            ),
        )

    def test_execute_performs_full_readback_and_rejects_remaining_missing(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.MISSING}
        )
        adapter.leave_missing.add(self.missing_id)
        prepared = coordinator.prepare()
        inspections_before_execute = len(adapter.inspect_calls)

        with self.assertRaisesRegex(
            ProvisioningExecutionError,
            "readback.*missing",
        ):
            coordinator.execute(self.authorization(prepared))

        self.assertEqual(adapter.create_calls, [self.missing_id])
        self.assertEqual(
            len(adapter.inspect_calls) - inspections_before_execute,
            2 * len(requirements_for_endpoint(store())),
        )

    def test_same_process_replay_of_preparation_identity_is_rejected(self):
        coordinator, adapter = coordinator_with_states({})
        prepared = coordinator.prepare()
        authorization = self.authorization(prepared)

        coordinator.execute(authorization)
        with self.assertRaisesRegex(ProvisioningError, "already attempted"):
            coordinator.execute(authorization)

        self.assertEqual(adapter.create_calls, [])

    def test_fabricated_preparation_identity_is_rejected_before_create(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.MISSING}
        )
        prepared = coordinator.prepare()
        authorization = ProvisioningAuthorization(
            fingerprint=prepared.fingerprint,
            preparation_id="prep_" + "9" * 43,
            approval_reference="human-gate-forged",
        )

        with self.assertRaisesRegex(ProvisioningError, "not issued"):
            coordinator.execute(authorization)

        self.assertEqual(adapter.create_calls, [])

    def test_two_coordinators_share_one_endpoint_execution_guard(self):
        endpoint = store(repository="owner/concurrency-docs")
        adapter = FakeProvisioningAdapter(
            endpoint,
            states={self.missing_id: ProvisioningResourceState.MISSING},
        )
        adapter.first_create_entered = Event()
        adapter.release_first_create = Event()
        first = ProvisioningCoordinator(
            endpoint,
            adapter,
            attempt_store=adapter.attempt_store,
            preparation_id_factory=adapter.preparation_ids,
        )
        second = ProvisioningCoordinator(
            endpoint,
            adapter,
            attempt_store=adapter.attempt_store,
            preparation_id_factory=adapter.preparation_ids,
        )
        prepared = first.prepare()
        self.assertEqual(prepared.fingerprint, second.prepare().fingerprint)
        authorization = self.authorization(prepared)
        outcomes = []
        errors = []

        def execute(coordinator):
            try:
                outcomes.append(coordinator.execute(authorization))
            except Exception as error:
                errors.append(error)

        first_thread = Thread(target=execute, args=(first,))
        second_thread = Thread(target=execute, args=(second,))
        first_thread.start()
        self.assertTrue(adapter.first_create_entered.wait(timeout=5))
        second_thread.start()
        second_thread.join(timeout=0.2)
        adapter.release_first_create.set()
        first_thread.join(timeout=5)
        second_thread.join(timeout=5)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(adapter.create_calls, [self.missing_id])
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ProvisioningError)
        self.assertRegex(
            str(errors[0]),
            "already attempted|fingerprint changed",
        )

    def test_partial_failure_reports_succeeded_and_failed_identities(self):
        coordinator, adapter = coordinator_with_states(
            {
                self.missing_id: ProvisioningResourceState.MISSING,
                self.second_missing_id: ProvisioningResourceState.MISSING,
            }
        )
        adapter.fail_on = self.second_missing_id
        prepared = coordinator.prepare()

        with self.assertRaises(ProvisioningExecutionError) as raised:
            coordinator.execute(
                self.authorization(prepared),
                preflight_calls=prepared.check.calls,
            )

        self.assertEqual(
            raised.exception.successful_stable_ids,
            (self.missing_id,),
        )
        self.assertEqual(
            raised.exception.failed_stable_id,
            self.second_missing_id,
        )
        self.assertEqual(
            adapter.create_calls,
            [self.missing_id, self.second_missing_id],
        )
        required_ids = tuple(
            requirement.name for requirement in prepared.check.requirements
        )
        self.assertEqual(
            tuple(
                (call.operation, call.stable_id)
                for call in raised.exception.provider_calls
            ),
            (
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                ("create", self.missing_id),
                ("create", self.second_missing_id),
            ),
        )

    def test_new_preparation_after_partial_success_proposes_only_remainder(self):
        coordinator, adapter = coordinator_with_states(
            {
                self.missing_id: ProvisioningResourceState.MISSING,
                self.second_missing_id: ProvisioningResourceState.MISSING,
            }
        )
        adapter.fail_on = self.second_missing_id
        prepared = coordinator.prepare()
        with self.assertRaises(ProvisioningExecutionError):
            coordinator.execute(self.authorization(prepared))

        replacement = ProvisioningCoordinator(
            adapter.endpoint,
            adapter,
            attempt_store=adapter.attempt_store,
            preparation_id_factory=adapter.preparation_ids,
        ).prepare()

        self.assertEqual(
            tuple(action.stable_id for action in replacement.actions),
            (self.second_missing_id,),
        )

    def test_failed_first_action_allows_new_gate_for_same_content(self):
        coordinator, adapter = coordinator_with_states(
            {self.missing_id: ProvisioningResourceState.MISSING}
        )
        adapter.fail_on = self.missing_id
        first = coordinator.prepare()

        with self.assertRaises(ProvisioningExecutionError) as raised:
            coordinator.execute(self.authorization(first))

        self.assertEqual(raised.exception.successful_stable_ids, ())
        self.assertEqual(
            raised.exception.failed_stable_id,
            self.missing_id,
        )
        adapter.fail_on = None
        replacement = coordinator.prepare()

        self.assertEqual(replacement.fingerprint, first.fingerprint)
        self.assertNotEqual(replacement.preparation_id, first.preparation_id)
        receipt = coordinator.execute(self.authorization(replacement))
        self.assertEqual(
            tuple(item.stable_id for item in receipt.action_receipts),
            (self.missing_id,),
        )

    def test_failed_noop_readback_consumes_identity_and_allows_new_gate(self):
        coordinator, adapter = coordinator_with_states({})
        first = coordinator.prepare()
        adapter.fail_inspect_at = 11

        with self.assertRaises(ProvisioningExecutionError) as raised:
            coordinator.execute(
                self.authorization(first),
                preflight_calls=first.check.calls,
            )

        required_ids = tuple(
            requirement.name for requirement in first.check.requirements
        )
        self.assertEqual(raised.exception.successful_stable_ids, ())
        self.assertEqual(
            raised.exception.failed_stable_id,
            required_ids[0],
        )
        self.assertEqual(
            tuple(
                (call.operation, call.stable_id)
                for call in raised.exception.provider_calls
            ),
            (
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                ("inspect", required_ids[0]),
            ),
        )
        with self.assertRaisesRegex(ProvisioningError, "already attempted"):
            coordinator.execute(self.authorization(first))

        adapter.fail_inspect_at = None
        replacement = coordinator.prepare()
        self.assertEqual(replacement.fingerprint, first.fingerprint)
        self.assertNotEqual(replacement.preparation_id, first.preparation_id)
        receipt = coordinator.execute(self.authorization(replacement))
        self.assertEqual(receipt.action_receipts, ())

    def test_success_noop_call_ledger_preserves_preflight_reprepare_and_readback(self):
        coordinator, _adapter = coordinator_with_states({})
        prepared = coordinator.prepare()
        required_ids = tuple(
            requirement.name for requirement in prepared.check.requirements
        )

        receipt = coordinator.execute(
            self.authorization(prepared),
            preflight_calls=prepared.check.calls,
        )

        self.assertEqual(
            tuple(
                (call.operation, call.stable_id)
                for call in receipt.calls
            ),
            (
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
            ),
        )


if __name__ == "__main__":
    unittest.main()
