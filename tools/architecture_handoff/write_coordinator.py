import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from threading import Lock
from typing import Mapping, Protocol

from .models import WorkRoute
from .preflight import (
    CandidateLane,
    CandidateSource,
    PreflightBundle,
    PreflightSourceKind,
    SourceApplicability,
    SourceDeclaration,
    run_preflight,
)
from .registry import (
    ProviderEndpointConfig,
    StoreConfig,
    StoreRole,
    TargetConfig,
)
from .runtime_config import QueryBudget
from .write_models import (
    IntakeState,
    ProtocolItemKind,
    TypedRelation,
    WriteIntent,
    WriteOperation,
    validate_intent,
)


class CandidateDisposition(str, Enum):
    REUSE_OR_REOPEN = "reuse-or-reopen"
    LINK_AND_NARROW = "link-and-narrow"
    SUPERSEDE = "supersede"
    CREATE_DISTINCT = "create-distinct"


@dataclass(frozen=True)
class NormalizedReadback:
    provider: str
    provider_id: str
    provider_qualified_id: str
    url: str
    provider_state: str
    comparable_payload_json: str


class WriteAdapter(Protocol):
    target: ProviderEndpointConfig

    def render_payload(
        self,
        intent: WriteIntent,
    ) -> Mapping[str, object]:
        ...

    def create_item(
        self,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        ...

    def update_item(
        self,
        provider_id: str,
        payload: Mapping[str, object],
        expected_state: str,
    ) -> Mapping[str, object]:
        ...

    def get_item(self, provider_id: str) -> Mapping[str, object]:
        ...

    def normalize_readback(
        self,
        payload: Mapping[str, object],
    ) -> NormalizedReadback:
        ...


@dataclass(frozen=True)
class WriteTargetConfig:
    target: ProviderEndpointConfig
    declarations: tuple[SourceDeclaration, ...]


@dataclass(frozen=True)
class PreparedWrite:
    target_config: WriteTargetConfig
    intent: WriteIntent
    preflight: PreflightBundle
    disposition: CandidateDisposition
    disposition_reason: str | None
    provider_payload_json: str
    fingerprint: str


@dataclass(frozen=True)
class WriteAuthorization:
    fingerprint: str
    approval_reference: str


@dataclass(frozen=True)
class WriteReceipt:
    operation: WriteOperation
    target_key: str
    provider: str
    provider_id: str
    provider_qualified_id: str
    url: str
    route: WorkRoute | None
    lifecycle_state: str | None
    intake_state: IntakeState | None
    relations: tuple[TypedRelation, ...]
    correlation_id: str | None
    preflight: PreflightBundle
    verified_payload_fingerprint: str


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        converted = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            converted[key] = _jsonable(item)
        return converted
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(
        f"value is not JSON-compatible: {type(value).__name__}"
    )


def canonical_json(value) -> str:
    try:
        return json.dumps(
            _jsonable(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("value is not canonical JSON") from error


def _payload_fingerprint(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _prepared_fingerprint(
    target_config: WriteTargetConfig,
    intent: WriteIntent,
    preflight: PreflightBundle,
    disposition: CandidateDisposition,
    disposition_reason: str | None,
    provider_payload_json: str,
) -> str:
    material = canonical_json(
        {
            "disposition": disposition,
            "disposition_reason": disposition_reason,
            "intent": intent,
            "preflight": preflight,
            "provider_payload": json.loads(provider_payload_json),
            "target_config": target_config,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _candidate_ids(preflight: PreflightBundle) -> set[str]:
    return {
        candidate.provider_qualified_id
        for result in (
            preflight.results
            + tuple(
                lane.result for lane in preflight.candidate_lanes
            )
        )
        for candidate in result.candidates
    }


def _require_non_empty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def validate_intent_endpoint(
    intent: WriteIntent,
    endpoint: ProviderEndpointConfig,
) -> None:
    if intent.item_kind is ProtocolItemKind.RETURN_ITEM:
        if (
            not isinstance(endpoint, StoreConfig)
            or endpoint.role is not StoreRole.DOCUMENTATION_INTAKE
        ):
            raise ValueError(
                "Return Item requires a documentation-intake store"
            )
    elif not isinstance(endpoint, TargetConfig):
        raise ValueError(
            "Work Item requires an implementation target"
        )


def _validate_disposition(
    intent: WriteIntent,
    preflight: PreflightBundle,
    disposition: CandidateDisposition,
    reason: str | None,
) -> None:
    if not isinstance(disposition, CandidateDisposition):
        raise ValueError("disposition must be a CandidateDisposition")
    candidate_ids = _candidate_ids(preflight)
    if (
        disposition is CandidateDisposition.CREATE_DISTINCT
        and candidate_ids
    ):
        _require_non_empty(
            reason,
            "create-distinct requires a reason",
        )
    if disposition in {
        CandidateDisposition.LINK_AND_NARROW,
        CandidateDisposition.SUPERSEDE,
    } and not candidate_ids.intersection(intent.related_items):
        raise ValueError(
            f"{disposition.value} requires a related candidate identity"
        )
    if (
        disposition is CandidateDisposition.REUSE_OR_REOPEN
        and not candidate_ids
    ):
        raise ValueError("reuse-or-reopen requires an existing candidate")


def _validate_normalized_readback(
    readback: NormalizedReadback,
) -> None:
    if not isinstance(readback, NormalizedReadback):
        raise ValueError("adapter returned invalid normalized readback")
    _require_non_empty(readback.provider, "provider")
    _require_non_empty(readback.provider_id, "provider_id")
    _require_non_empty(
        readback.provider_qualified_id,
        "provider_qualified_id",
    )
    _require_non_empty(readback.url, "url")
    _require_non_empty(readback.provider_state, "provider_state")
    _require_non_empty(
        readback.comparable_payload_json,
        "comparable_payload_json",
    )


class WriteCoordinator:
    def __init__(
        self,
        target_config: WriteTargetConfig,
        adapter: WriteAdapter,
        sources: tuple[CandidateSource, ...],
        *,
        preflight_budget: QueryBudget,
        candidate_lanes: tuple[CandidateLane, ...] = (),
    ):
        if not isinstance(preflight_budget, QueryBudget):
            raise ValueError("preflight_budget must be a QueryBudget")
        if not isinstance(target_config, WriteTargetConfig):
            raise ValueError(
                "target_config must be a WriteTargetConfig"
            )
        target = target_config.target
        if not isinstance(target, (TargetConfig, StoreConfig)):
            raise ValueError(
                "target must be a provider endpoint config"
            )
        if target.routing_status != "active":
            raise ValueError(
                f"write target must be active: {target.routing_status}"
            )
        if getattr(adapter, "target", None) != target:
            raise ValueError("adapter target does not match write target")
        declarations_by_kind = {}
        for declaration in target_config.declarations:
            if not isinstance(declaration, SourceDeclaration):
                raise ValueError(
                    "target declarations must contain "
                    "SourceDeclaration values"
                )
            if not isinstance(
                declaration.kind,
                PreflightSourceKind,
            ):
                raise ValueError(
                    "target source declaration kind is invalid"
                )
            if not isinstance(
                declaration.applicability,
                SourceApplicability,
            ):
                raise ValueError(
                    "target source applicability is invalid"
                )
            if declaration.kind in declarations_by_kind:
                raise ValueError(
                    "target source declaration is duplicated: "
                    f"{declaration.kind.value}"
                )
            declarations_by_kind[declaration.kind] = declaration
        sources_by_kind = {}
        for source in sources:
            if getattr(source, "target", None) != target:
                raise ValueError(
                    "candidate source target does not match write target"
                )
            kind = getattr(source, "kind", None)
            if not isinstance(kind, PreflightSourceKind):
                raise ValueError("candidate source kind is invalid")
            if kind in sources_by_kind:
                raise ValueError(
                    f"candidate source is duplicated: {kind.value}"
                )
            sources_by_kind[kind] = source
        enabled_kinds = {
            declaration.kind
            for declaration in target_config.declarations
            if declaration.applicability
            is SourceApplicability.ENABLED
        }
        not_applicable_kinds = set(declarations_by_kind) - enabled_kinds
        hidden = not_applicable_kinds.intersection(sources_by_kind)
        if hidden:
            kind = sorted(item.value for item in hidden)[0]
            raise ValueError(
                "not-applicable source must not have an adapter: "
                f"{kind}"
            )
        if set(sources_by_kind) != enabled_kinds:
            raise ValueError(
                "enabled target sources must match bound adapters"
            )
        if not isinstance(candidate_lanes, tuple):
            raise ValueError("candidate_lanes must be a tuple")
        lane_names = set()
        for lane in candidate_lanes:
            if not isinstance(lane, CandidateLane):
                raise ValueError(
                    "candidate_lanes must contain CandidateLane values"
                )
            if (
                not isinstance(lane.name, str)
                or not lane.name.strip()
            ):
                raise ValueError(
                    "candidate lane name must be a non-empty string"
                )
            if lane.name in lane_names:
                raise ValueError(
                    f"candidate lane is duplicated: {lane.name}"
                )
            lane_names.add(lane.name)
            if getattr(lane.source, "target", None) != target:
                raise ValueError(
                    "candidate lane source target does not match "
                    "write target"
                )
        self._target_config = target_config
        self._adapter = adapter
        self._sources = sources
        self._candidate_lanes = candidate_lanes
        self._preflight_budget = preflight_budget
        self._attempted_fingerprints: set[str] = set()
        self._attempt_lock = Lock()

    def prepare(
        self,
        intent: WriteIntent,
        disposition: CandidateDisposition,
        disposition_reason: str | None = None,
    ) -> PreparedWrite:
        return self._prepare(
            intent,
            disposition,
            disposition_reason,
            validate_disposition=True,
        )

    def _prepare(
        self,
        intent: WriteIntent,
        disposition: CandidateDisposition,
        disposition_reason: str | None,
        *,
        validate_disposition: bool,
    ) -> PreparedWrite:
        validate_intent(intent)
        if intent.target_key != self._target_config.target.key:
            raise ValueError(
                "intent target does not match configured write target"
            )
        validate_intent_endpoint(
            intent,
            self._target_config.target,
        )
        preflight = run_preflight(
            intent,
            self._target_config.declarations,
            self._sources,
            limit=min(
                self._preflight_budget.page_size,
                self._preflight_budget.max_items,
            ),
            candidate_lanes=self._candidate_lanes,
        )
        if validate_disposition:
            _validate_disposition(
                intent,
                preflight,
                disposition,
                disposition_reason,
            )
        provider_payload = self._adapter.render_payload(intent)
        if not isinstance(provider_payload, Mapping):
            raise ValueError("adapter render_payload must return a mapping")
        provider_payload_json = canonical_json(provider_payload)
        fingerprint = _prepared_fingerprint(
            self._target_config,
            intent,
            preflight,
            disposition,
            disposition_reason,
            provider_payload_json,
        )
        return PreparedWrite(
            target_config=self._target_config,
            intent=intent,
            preflight=preflight,
            disposition=disposition,
            disposition_reason=disposition_reason,
            provider_payload_json=provider_payload_json,
            fingerprint=fingerprint,
        )

    def execute(
        self,
        prepared: PreparedWrite,
        authorization: WriteAuthorization,
    ) -> WriteReceipt:
        if not isinstance(prepared, PreparedWrite):
            raise ValueError("prepared must be a PreparedWrite")
        if not isinstance(authorization, WriteAuthorization):
            raise ValueError("authorization must be a WriteAuthorization")
        _require_non_empty(
            authorization.approval_reference,
            "approval_reference",
        )
        if authorization.fingerprint != prepared.fingerprint:
            raise ValueError(
                "authorization fingerprint does not match prepared write"
            )
        if prepared.target_config != self._target_config:
            raise ValueError(
                "prepared target does not match coordinator target"
            )
        if (
            prepared.disposition
            is CandidateDisposition.REUSE_OR_REOPEN
        ):
            raise ValueError(
                "reuse-or-reopen does not create a new item; "
                "prepare a separate update"
            )

        current = self._prepare(
            prepared.intent,
            prepared.disposition,
            prepared.disposition_reason,
            validate_disposition=False,
        )
        if current.fingerprint != prepared.fingerprint:
            raise ValueError("prepared write is stale")

        with self._attempt_lock:
            if prepared.fingerprint in self._attempted_fingerprints:
                raise ValueError("prepared write was already attempted")
            self._attempted_fingerprints.add(prepared.fingerprint)

        provider_payload = json.loads(prepared.provider_payload_json)
        if prepared.intent.operation is WriteOperation.CREATE:
            write_response = self._adapter.create_item(provider_payload)
        else:
            write_response = self._adapter.update_item(
                prepared.intent.provider_id,
                provider_payload,
                prepared.intent.expected_provider_state,
            )
        initial = self._adapter.normalize_readback(write_response)
        _validate_normalized_readback(initial)

        provider_payload = self._adapter.get_item(initial.provider_id)
        readback = self._adapter.normalize_readback(provider_payload)
        _validate_normalized_readback(readback)
        if readback.provider != self._target_config.target.provider:
            raise ValueError(
                "readback provider does not match configured target"
            )
        if (
            readback.comparable_payload_json
            != prepared.provider_payload_json
        ):
            raise ValueError("readback payload mismatch")

        return WriteReceipt(
            operation=prepared.intent.operation,
            target_key=prepared.intent.target_key,
            provider=readback.provider,
            provider_id=readback.provider_id,
            provider_qualified_id=readback.provider_qualified_id,
            url=readback.url,
            route=prepared.intent.route,
            lifecycle_state=prepared.intent.lifecycle_state,
            intake_state=prepared.intent.intake_state,
            relations=prepared.intent.relations,
            correlation_id=prepared.intent.correlation_id,
            preflight=current.preflight,
            verified_payload_fingerprint=_payload_fingerprint(
                readback.comparable_payload_json
            ),
        )
