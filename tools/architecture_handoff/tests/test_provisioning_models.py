import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.protocol_metadata import (  # noqa: E402
    INTAKE_STATE_LABELS,
    RETURN_KIND_LABELS,
    STATUS_LABELS,
    WORK_ROUTE_LABELS,
)
from tools.architecture_handoff.provisioning_models import (  # noqa: E402
    PreparedProvisioning,
    ProvisioningAction,
    ProvisioningActionReceipt,
    ProvisioningAuthorization,
    ProvisioningCall,
    ProvisioningCheck,
    ProvisioningObservation,
    ProvisioningReceipt,
    ProvisioningRequirement,
    ProvisioningResourceSpec,
    ProvisioningResourceState,
    requirements_for_endpoint,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    StoreConfig,
    StoreRole,
    TargetConfig,
)


def github_target(**overrides):
    values = {
        "key": "example-implementation",
        "provider": "github",
        "repository": "owner/pilot",
        "routing_status": "active",
        "owns": ("pilot",),
        "excludes": (),
    }
    values.update(overrides)
    return TargetConfig(**values)


def github_intake_store(**overrides):
    values = {
        "key": "documentation-intake",
        "role": StoreRole.DOCUMENTATION_INTAKE,
        "provider": "github",
        "repository": "owner/docs",
        "routing_status": "active",
    }
    values.update(overrides)
    return StoreConfig(**values)


def requirement(name="intake-state:pending"):
    family, _ = name.split(":", 1)
    return ProvisioningRequirement(family=family, name=name)


def resource(stable_id="intake-state:pending"):
    return ProvisioningResourceSpec(
        resource_type="label",
        stable_id=stable_id,
        create_payload_json=(
            '{"color":"FBCA04","description":"Awaiting handling",'
            f'"name":"{stable_id}"}}'
        ),
        presentation_json='{"color":"FBCA04","description":"Awaiting handling"}',
    )


PREPARATION_ID = "prep_" + "a" * 43


def observation(state=ProvisioningResourceState.SATISFIED):
    values = {
        "requirement": requirement(),
        "resource": resource(),
        "state": state,
    }
    if state is ProvisioningResourceState.SATISFIED:
        values["observed_identity"] = "intake-state:pending"
        values["observed_presentation_json"] = resource().presentation_json
    elif state is ProvisioningResourceState.MISSING:
        pass
    elif state is ProvisioningResourceState.CONFLICTING:
        values["limitation"] = "provider identity conflicts with requirement"
    return ProvisioningObservation(**values)


class ProvisioningModelTests(unittest.TestCase):
    def test_documentation_store_requires_only_return_labels(self):
        requirements = requirements_for_endpoint(github_intake_store())

        self.assertEqual(
            tuple(requirement.name for requirement in requirements),
            RETURN_KIND_LABELS + INTAKE_STATE_LABELS,
        )
        self.assertEqual(
            tuple(requirement.family for requirement in requirements),
            tuple(name.split(":", 1)[0] for name in requirements_name_tuple(requirements)),
        )

    def test_target_requires_only_route_and_status_labels(self):
        requirements = requirements_for_endpoint(github_target())

        self.assertEqual(
            tuple(requirement.name for requirement in requirements),
            WORK_ROUTE_LABELS + STATUS_LABELS,
        )

    def test_requirements_are_stable_and_models_are_frozen(self):
        first = requirements_for_endpoint(github_target())
        second = requirements_for_endpoint(github_target())
        specification = resource()

        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            specification.stable_id = "other"

    def test_style_drift_is_not_missing_or_conflicting(self):
        observation = ProvisioningObservation(
            requirement=requirement("intake-state:pending"),
            resource=resource("intake-state:pending"),
            state=ProvisioningResourceState.STYLE_DRIFT,
            observed_presentation_json='{"color":"ffffff"}',
        )

        self.assertIs(
            observation.state,
            ProvisioningResourceState.STYLE_DRIFT,
        )

    def test_rejects_blank_resource_identities_and_noncanonical_json(self):
        with self.assertRaisesRegex(ValueError, "family"):
            ProvisioningRequirement(family=" ", name="intake-state:pending")
        with self.assertRaisesRegex(ValueError, "name"):
            ProvisioningRequirement(family="intake-state", name=" ")
        with self.assertRaisesRegex(ValueError, "stable_id"):
            ProvisioningResourceSpec(
                resource_type="label",
                stable_id=" ",
                create_payload_json="{}",
                presentation_json="{}",
            )
        with self.assertRaisesRegex(ValueError, "canonical JSON"):
            ProvisioningResourceSpec(
                resource_type="label",
                stable_id="intake-state:pending",
                create_payload_json='{"name": "intake-state:pending"}',
                presentation_json="{}",
            )

    def test_rejects_duplicate_requirements_and_invalid_observation_states(self):
        pending = requirement()
        spec = resource()
        missing = ProvisioningObservation(
            requirement=pending,
            resource=spec,
            state=ProvisioningResourceState.MISSING,
        )

        with self.assertRaisesRegex(ValueError, "duplicate requirement"):
            ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending, pending),
                observations=(missing,),
            )
        with self.assertRaisesRegex(ValueError, "missing observation"):
            ProvisioningObservation(
                requirement=pending,
                resource=spec,
                state=ProvisioningResourceState.MISSING,
                observed_presentation_json='{"color":"ffffff"}',
            )
        with self.assertRaisesRegex(ValueError, "style-drift observation"):
            ProvisioningObservation(
                requirement=pending,
                resource=spec,
                state=ProvisioningResourceState.STYLE_DRIFT,
            )
        with self.assertRaisesRegex(ValueError, "conflicting observation"):
            ProvisioningObservation(
                requirement=pending,
                resource=spec,
                state=ProvisioningResourceState.CONFLICTING,
            )

    def test_models_preserve_provisioning_lifecycle_values(self):
        pending = requirement()
        action = ProvisioningAction(requirement=pending, resource=resource())
        call = ProvisioningCall(
            operation="create",
            resource_type="label",
            stable_id="intake-state:pending",
        )
        check = ProvisioningCheck(
            endpoint=github_intake_store(),
            requirements=(pending,),
            observations=(
                observation(ProvisioningResourceState.MISSING),
            ),
            calls=(call,),
        )
        prepared = PreparedProvisioning(
            check=check,
            actions=(action,),
            fingerprint="a" * 64,
            preparation_id=PREPARATION_ID,
        )
        authorization = ProvisioningAuthorization(
            fingerprint=prepared.fingerprint,
            preparation_id=prepared.preparation_id,
            approval_reference="human-gate-1",
        )
        readback = ProvisioningCheck(
            endpoint=github_intake_store(),
            requirements=(pending,),
            observations=(observation(),),
            calls=(call,),
        )
        receipt = ProvisioningReceipt(
            prepared=prepared,
            authorization=authorization,
            action_receipts=(
                ProvisioningActionReceipt(action=action, calls=(call,)),
            ),
            readback=readback,
            preflight_calls=(call,),
        )

        self.assertEqual(action.stable_id, "intake-state:pending")
        self.assertEqual(receipt.action_receipts[0].stable_id, action.stable_id)
        self.assertEqual(receipt.prepared.preparation_id, PREPARATION_ID)
        self.assertEqual(receipt.calls, (call, call, call, call))

    def test_preparation_identity_is_opaque_and_bound_to_authorization(self):
        pending = requirement()
        check = ProvisioningCheck(
            endpoint=github_intake_store(),
            requirements=(pending,),
            observations=(observation(ProvisioningResourceState.MISSING),),
        )
        prepared = PreparedProvisioning(
            check=check,
            actions=(ProvisioningAction(pending, resource()),),
            fingerprint="a" * 64,
            preparation_id=PREPARATION_ID,
        )

        with self.assertRaisesRegex(ValueError, "preparation_id"):
            replace(prepared, preparation_id="not-opaque")
        with self.assertRaisesRegex(ValueError, "preparation_id"):
            ProvisioningAuthorization(
                fingerprint=prepared.fingerprint,
                preparation_id="not-opaque",
                approval_reference="human-gate-1",
            )
        with self.assertRaisesRegex(ValueError, "preparation identity"):
            ProvisioningReceipt(
                prepared=prepared,
                authorization=ProvisioningAuthorization(
                    fingerprint=prepared.fingerprint,
                    preparation_id="prep_" + "b" * 43,
                    approval_reference="human-gate-1",
                ),
                action_receipts=(
                    ProvisioningActionReceipt(
                        action=prepared.actions[0],
                        calls=(
                            ProvisioningCall(
                                operation="create",
                                resource_type="label",
                                stable_id="intake-state:pending",
                            ),
                        ),
                    ),
                ),
                readback=ProvisioningCheck(
                    endpoint=github_intake_store(),
                    requirements=(pending,),
                    observations=(observation(),),
                ),
            )

    def test_success_receipt_requires_exact_actions_and_complete_readback(self):
        pending = requirement()
        action = ProvisioningAction(pending, resource())
        prepared = PreparedProvisioning(
            check=ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending,),
                observations=(observation(ProvisioningResourceState.MISSING),),
            ),
            actions=(action,),
            fingerprint="a" * 64,
            preparation_id=PREPARATION_ID,
        )
        authorization = ProvisioningAuthorization(
            fingerprint=prepared.fingerprint,
            preparation_id=prepared.preparation_id,
            approval_reference="human-gate-1",
        )
        complete = ProvisioningCheck(
            endpoint=github_intake_store(),
            requirements=(pending,),
            observations=(observation(),),
        )

        with self.assertRaisesRegex(ValueError, "exactly match"):
            ProvisioningReceipt(
                prepared=prepared,
                authorization=authorization,
                action_receipts=(),
                readback=complete,
            )

        invalid_readbacks = (
            ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending,),
                observations=(),
            ),
            ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending,),
                observations=(observation(ProvisioningResourceState.MISSING),),
            ),
            ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending,),
                observations=(
                    observation(ProvisioningResourceState.CONFLICTING),
                ),
            ),
        )
        for readback in invalid_readbacks:
            with self.subTest(readback=readback):
                with self.assertRaisesRegex(
                    ValueError,
                    "complete and non-conflicting",
                ):
                    ProvisioningReceipt(
                        prepared=prepared,
                        authorization=authorization,
                        action_receipts=(
                            ProvisioningActionReceipt(
                                action=action,
                                calls=(
                                    ProvisioningCall(
                                        operation="create",
                                        resource_type="label",
                                        stable_id=action.stable_id,
                                    ),
                                ),
                            ),
                        ),
                        readback=readback,
                    )

    def test_prepared_actions_match_ordered_missing_observations(self):
        pending = requirement()
        check = ProvisioningCheck(
            endpoint=github_intake_store(),
            requirements=(pending,),
            observations=(observation(ProvisioningResourceState.MISSING),),
        )

        with self.assertRaisesRegex(ValueError, "missing observations"):
            PreparedProvisioning(
                check=check,
                actions=(),
                fingerprint="a" * 64,
                preparation_id=PREPARATION_ID,
            )

    def test_success_receipt_derives_exact_phase_call_ledger(self):
        pending = requirement()
        inspect = ProvisioningCall(
            operation="inspect",
            resource_type="label",
            stable_id=pending.name,
        )
        create = ProvisioningCall(
            operation="create",
            resource_type="label",
            stable_id=pending.name,
        )
        action = ProvisioningAction(pending, resource())
        prepared = PreparedProvisioning(
            check=ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending,),
                observations=(observation(ProvisioningResourceState.MISSING),),
                calls=(inspect,),
            ),
            actions=(action,),
            fingerprint="a" * 64,
            preparation_id=PREPARATION_ID,
        )
        receipt = ProvisioningReceipt(
            prepared=prepared,
            authorization=ProvisioningAuthorization(
                fingerprint=prepared.fingerprint,
                preparation_id=prepared.preparation_id,
                approval_reference="human-gate-1",
            ),
            action_receipts=(
                ProvisioningActionReceipt(action=action, calls=(create,)),
            ),
            readback=ProvisioningCheck(
                endpoint=github_intake_store(),
                requirements=(pending,),
                observations=(observation(),),
                calls=(inspect,),
            ),
            preflight_calls=(inspect,),
        )

        self.assertEqual(
            receipt.calls,
            (inspect, inspect, create, inspect),
        )

    def test_conflicting_observation_preserves_safe_provider_metadata(self):
        conflicting = ProvisioningObservation(
            requirement=requirement(),
            resource=resource(),
            state=ProvisioningResourceState.CONFLICTING,
            observed_identity="Intake-State:Pending",
            observed_presentation_json=(
                '{"color":"FBCA04","description":"Existing presentation"}'
            ),
            limitation="GitHub label identity conflicts with requirement",
        )

        self.assertEqual(
            conflicting.observed_identity,
            "Intake-State:Pending",
        )
        with self.assertRaisesRegex(ValueError, "observed_identity"):
            replace(conflicting, observed_identity="unsafe\nidentity")

    def test_rejects_inactive_unknown_or_malformed_endpoints(self):
        for endpoint in (
            github_target(routing_status="suspended"),
            github_intake_store(routing_status="retired"),
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(ValueError, "active"):
                    requirements_for_endpoint(endpoint)

        with self.assertRaisesRegex(ValueError, "TargetConfig or StoreConfig"):
            requirements_for_endpoint(object())

        with self.assertRaisesRegex(ValueError, "StoreRole"):
            requirements_for_endpoint(
                github_intake_store(role="documentation-intake")
            )


def requirements_name_tuple(requirements):
    return tuple(requirement.name for requirement in requirements)


if __name__ == "__main__":
    unittest.main()
