import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
DOCUMENTATION_CONTRACT_AVAILABLE = all(
    (REPOSITORY_ROOT / relative_path).is_file()
    for relative_path in (
        "AGENTS.md",
        "handbook/architecture-to-openspec-handoff.md",
        "processes/architecture-to-openspec-handoff.md",
    )
)
requires_documentation_repository = unittest.skipUnless(
    DOCUMENTATION_CONTRACT_AVAILABLE,
    "documentation repository contract is not present",
)


def read_repository_file(relative_path):
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def markdown_section(document, heading):
    start_marker = f"{heading}\n"
    start = document.index(start_marker) + len(start_marker)
    level = len(heading) - len(heading.lstrip("#"))
    match = re.search(
        rf"^#{{1,{level}}} ",
        document[start:],
        flags=re.MULTILINE,
    )
    end = start + match.start() if match else len(document)
    return document[start:end]


class DocumentationOperationsContractTests(unittest.TestCase):
    @requires_documentation_repository
    def test_endpoint_setup_guidance_is_role_aware_and_approval_gated(self):
        process = read_repository_file(
            "processes/architecture-to-openspec-handoff.md"
        )
        handbook = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        package = read_repository_file(
            "tools/architecture_handoff/README.md"
        )
        github_design = read_repository_file(
            "tools/architecture_handoff/design/github-adapter.md"
        )
        instructions = read_repository_file("AGENTS.md")

        self.assertIn("## Provider Endpoint Setup", process)
        setup_contract = markdown_section(
            process,
            "## Provider Endpoint Setup",
        )
        compact_setup_contract = " ".join(setup_contract.split())
        for required in (
            "explicit and on demand",
            "Implementation target",
            "`work-route:*` and `status:*`",
            "Documentation intake store",
            "`return-kind:*` and `intake-state:*`",
            "Prepare",
            "exact provisioning preview",
            "opaque preparation identity",
            "deterministic content fingerprint",
            "Endpoint Setup Human Gate",
            "Execute",
            "atomically consumes",
            "does not retry",
            "style drift is advisory",
            "ordered provider call ledger",
            "preflight Check",
            "outside the repository",
            "issued and consumed preparation state",
            "binds one opaque preparation identity to its content fingerprint",
            "not a provider-resource cache or derived search index",
            "does not scan, delete, rename, or rewrite style",
            "Target Adoption invokes",
            "does not create another `work-route`",
            "does not create an adoption artifact",
            "does not create an Architecture Slice Brief",
            "does not create another slice artifact",
        ):
            self.assertIn(required, compact_setup_contract)

        for guide_name, guide in (
            ("handbook", handbook),
            ("package", package),
        ):
            compact_guide = " ".join(guide.split())
            for required in (
                "python3 -m tools.architecture_handoff.setup_cli prepare",
                "python3 -m tools.architecture_handoff.setup_cli execute",
                "--target example-implementation",
                "--store example-documentation-intake",
                "--expected-fingerprint",
                "--preparation-id",
                "--approval-reference",
                "exact preview",
                "Endpoint Setup Human Gate",
                "style_drift",
                "empty `actions`",
                "partial success",
                "new Prepare",
                "provider readback",
                "ordered provider call ledger",
                "preflight Check",
                "local replay ledger",
                "issued or consumed state",
                "gh auth login",
                "gh auth status",
                'GITHUB_TOKEN="$(gh auth token)"',
                "does not create an Architecture Slice Brief",
                "does not create another slice artifact",
            ):
                self.assertIn(
                    required,
                    compact_guide,
                    f"{guide_name} missing {required!r}",
                )

        github_setup = markdown_section(
            github_design,
            "## GitHub Label Provisioning",
        )
        compact_github_setup = " ".join(github_setup.split())
        for required in (
            "GitHub-only rollout",
            "GET /repos/{owner}/{repository}/labels/{name}",
            "POST /repos/{owner}/{repository}/labels",
            "does not list, scan, rename, delete, or rewrite",
            "GitLab, Jira, and Markdown provisioning remain unsupported",
        ):
            self.assertIn(required, compact_github_setup)

        operations = markdown_section(
            instructions,
            "## Architecture-to-OpenSpec Handoff Operations",
        )
        compact_operations = " ".join(operations.split())
        for required in (
            "target-side adoption instructions",
            "local setup",
            "setup_cli prepare",
            "exact preview",
            "Endpoint Setup Human Gate",
            "setup_cli execute",
            "provider readback",
            "does not create an Architecture Slice Brief",
            "does not create another slice artifact",
        ):
            self.assertIn(required, compact_operations)

    def test_package_documents_two_phase_return_writer(self):
        readme = read_repository_file(
            "tools/architecture_handoff/README.md"
        )

        for required in (
            "python3 -m tools.architecture_handoff.return_cli prepare",
            "python3 -m tools.architecture_handoff.return_cli execute",
            "--runtime architecture-handoff.runtime.json",
            "--input /path/to/return-input.json",
            "--expected-fingerprint",
            "--approval-reference",
            "exact provider payload",
            "does not retry",
        ):
            self.assertIn(required, readme)

    @requires_documentation_repository
    def test_return_intake_commands_resolve_store_and_runtime_policy(self):
        handbook = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        package = read_repository_file(
            "tools/architecture_handoff/README.md"
        )
        guidance = "\n".join((handbook, package))

        for required in (
            "--store example-documentation-intake",
            "--runtime architecture-handoff.runtime.json",
            "documentation intake store",
            "tracked runtime ceiling",
            "raw provider records",
            "blocks",
        ):
            self.assertIn(required, guidance)

        return_example = markdown_section(
            package,
            "## Run advanced read operations",
        ).split("Use `trace`", 1)[0]
        self.assertIn("--store example-documentation-intake", return_example)
        self.assertNotIn("--target example-implementation", return_example)
        self.assertIn(
            "python3 -m tools.architecture_handoff get",
            guidance,
        )

    @requires_documentation_repository
    def test_operator_guidance_uses_canonical_registry_and_gh_auth(self):
        repository_readme = read_repository_file("README.md")
        handbook = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        package = read_repository_file(
            "tools/architecture_handoff/README.md"
        )
        guidance = "\n".join((handbook, package))

        for command in (
            "gh auth login",
            "gh auth status",
            'GITHUB_TOKEN="$(gh auth token)"',
            "--registry architecture-handoff.registry.json",
        ):
            self.assertIn(command, guidance)
        self.assertIn("existing `gh` keyring session", guidance)
        self.assertIn("CI", guidance)
        self.assertNotIn(
            "tools/architecture_handoff/example-registry.json",
            guidance,
        )
        self.assertIn(
            "[Project Target Registry](architecture-handoff.registry.json)",
            repository_readme,
        )
        self.assertIn(
            "[Architecture-to-OpenSpec Operations]"
            "(handbook/architecture-to-openspec-handoff.md)",
            repository_readme,
        )

    def test_compatibility_input_guidance_marks_example_shape_only(self):
        design = read_repository_file(
            "tools/architecture_handoff/design/write-coordinator.md"
        )
        compact_design = " ".join(design.split())

        self.assertIn("example-brief-input.json", compact_design)
        self.assertIn("shape-only example", compact_design)
        self.assertIn("all-zero revision", compact_design)
        self.assertIn(
            "/path/to/prepared-brief-input.json",
            compact_design,
        )
        self.assertNotIn("example-input.json", compact_design)

    @requires_documentation_repository
    def test_tracked_guidance_exposes_bounded_advanced_read_operations(self):
        process = read_repository_file(
            "processes/architecture-to-openspec-handoff.md"
        )
        handbook = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        instructions = read_repository_file("AGENTS.md")
        readme = read_repository_file("tools/architecture_handoff/README.md")
        tracked_guidance = "\n".join(
            (process, handbook, instructions, readme)
        )

        for required_text in (
            "required predicates",
            "advisory candidate enrichment",
            "one provider page",
            "continuation cursor",
            "no derived index",
            "GitHub semantic",
            "human semantic disposition",
        ):
            self.assertIn(required_text, tracked_guidance)

        for operator_example in (
            "show pending evidence returns",
            "trace correlation corr-12",
            "find work still citing revision X for ADR-0003",
            "find similar work for capability Y",
        ):
            self.assertIn(operator_example, tracked_guidance)

        self.assertIn("English source guidance", tracked_guidance)
        self.assertIn("session language", tracked_guidance)
        self.assertIn("explicit continuation", tracked_guidance)
        self.assertIn("drill-down", tracked_guidance)

    @requires_documentation_repository
    def test_canonical_process_states_advanced_github_boundaries(self):
        process = read_repository_file(
            "processes/architecture-to-openspec-handoff.md"
        )
        capabilities = markdown_section(
            process,
            "### Adapter Search Capabilities",
        )

        for supported_boundary in (
            "native exact label filters",
            "partial body search",
            "authenticated semantic and hybrid candidate retrieval",
            "revision inequality",
            "graph reconstruction",
            "one provider page",
            "required incomplete lanes",
            "negative duplicate claim",
        ):
            self.assertIn(supported_boundary, capabilities)

        self.assertIn(
            "New GitLab, Jira, and Markdown adapters remain outside",
            capabilities,
        )
        self.assertNotIn(
            "semantic matching, full graph reconstruction, and a dedicated "
            "stale-revision index remain outside",
            capabilities,
        )
        self.assertNotIn(
            "A bounded adapter-side filter is acceptable",
            capabilities,
        )
        self.assertIn(
            "Missing provider predicates remain partial or unsupported",
            capabilities,
        )
        self.assertIn(
            "Only explicit bounded coordinator or agent composition may "
            "continue or filter returned pages",
            capabilities,
        )
        self.assertIn(
            "Adapters never emulate a missing predicate",
            capabilities,
        )

    @requires_documentation_repository
    def test_guidance_uses_revision_independent_canonical_source_identity(self):
        process = read_repository_file(
            "processes/architecture-to-openspec-handoff.md"
        )
        handbook = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        readme = read_repository_file("tools/architecture_handoff/README.md")
        guidance = "\n".join((process, handbook, readme))
        canonical = (
            "git:https://github.com/organization/documentation:"
            "architecture/09-architecture-decisions.md#adr-0003"
        )

        self.assertIn(canonical, guidance)
        self.assertIn(
            "relation target is revision-independent",
            guidance,
        )
        self.assertIn(
            "pinned revision remains only in `relation.revision`",
            guidance,
        )
        self.assertNotIn(
            "git:example-documentation@04afd58:",
            readme,
        )

    @requires_documentation_repository
    def test_agent_entry_point_uses_canonical_on_demand_contract(self):
        instructions = read_repository_file("AGENTS.md")
        operations = markdown_section(
            instructions,
            "## Architecture-to-OpenSpec Handoff Operations",
        )

        self.assertIn(
            "[[processes/architecture-to-openspec-handoff|",
            operations,
        )
        self.assertIn(
            "[[handbook/architecture-to-openspec-handoff|",
            operations,
        )
        self.assertIn("tasks, remaining work, or expected results", operations)
        self.assertIn("Do not poll at session start", operations)
        self.assertIn("target task store", operations)
        self.assertIn("documentation intake store", operations)
        self.assertIn("compact records", operations)
        self.assertIn("one record", operations)
        self.assertIn("full payload", operations)
        self.assertIn("current session language", operations)
        self.assertNotIn("The pilot route is provisional", instructions)
        self.assertNotIn(
            "require one accepted product requirement plus accepted ADR",
            instructions,
        )
        self.assertNotIn(
            "tools/architecture-slice-handoff/render_github_issue.py",
            instructions,
        )

    @requires_documentation_repository
    def test_handbook_covers_the_four_operator_flows(self):
        guide = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        index = read_repository_file("handbook/README.md")
        summary = markdown_section(guide, "## Summarize Available Work")
        inspection = markdown_section(guide, "## Inspect a Selected Item")
        normalized_summary = " ".join(summary.split())
        normalized_inspection = " ".join(inspection.split())

        self.assertIn(
            "[[processes/architecture-to-openspec-handoff|"
            "Architecture-to-OpenSpec Handoff]]",
            guide,
        )
        self.assertIn(
            "[[processes/research-and-discovery-planning|"
            "Research and Product Discovery Planning]]",
            guide,
        )
        for heading in (
            "## Summarize Available Work",
            "## Inspect a Selected Item",
            "## Triage Return Items",
            "## Record Experiment Evidence",
        ):
            self.assertIn(heading, guide)
        self.assertIn("### Target Task Store", normalized_summary)
        self.assertIn("active items by `work-route`", normalized_summary)
        self.assertIn("### Documentation Intake Store", normalized_summary)
        self.assertIn(
            "pending Return Items by `return-kind`",
            normalized_summary,
        )
        self.assertIn("completeness", normalized_summary)
        self.assertIn("current session language", normalized_summary)
        self.assertIn("category", normalized_inspection)
        self.assertIn("compact records", normalized_inspection)
        self.assertIn("one record", normalized_inspection)
        self.assertIn("full payload", normalized_inspection)
        self.assertIn("### Target Task", normalized_inspection)
        self.assertIn(
            "readiness, blockers, and linked sources",
            normalized_inspection,
        )
        self.assertIn("### Return Item", normalized_inspection)
        self.assertIn(
            "correlation ID and typed source relation",
            normalized_inspection,
        )
        self.assertNotIn("domain-model question", guide)
        self.assertIn("intake-state: handled", guide)
        self.assertIn(
            "[[handbook/architecture-to-openspec-handoff|"
            "Architecture-to-OpenSpec Operations]]",
            index,
        )

    @requires_documentation_repository
    def test_canonical_process_defines_documentation_intake_sequence(self):
        process = read_repository_file(
            "processes/architecture-to-openspec-handoff.md"
        )
        discovery = markdown_section(
            process,
            "## On-Demand Task Discovery",
        )
        intake = markdown_section(
            process,
            "### Documentation-Side Intake",
        )
        normalized_discovery = " ".join(discovery.split())
        normalized_intake = " ".join(intake.split())

        for required_text in (
            "### Documentation-Side Intake",
            "After the user selects a category, return compact records",
            "Load the full payload and linked sources only after the user "
            "selects one record",
        ):
            self.assertIn(required_text, normalized_discovery)

        for required_text in (
            "Resolve the configured documentation intake target",
            "Report compact counts by `return-kind`",
            "Load the full Return Item only after the user selects one record",
            "Validate its correlation ID, typed source relation",
            "Create or link the durable follow-up",
            "prepare a separately authorized `pending -> handled` update",
        ):
            self.assertIn(required_text, normalized_intake)

        for hint_row in (
            "| Architecture Slice Handoff | Implements one bounded outcome "
            "from accepted product or architecture sources through the "
            "OpenSpec workflow. |",
            "| Implementation Conformance Referral | Corrects a target that "
            "conflicts with an accepted source or earlier Brief without "
            "introducing new product or architecture meaning. |",
            "| Spike / Evidence | Answers one bounded question and returns "
            "durable Evidence before dependent work continues. |",
            "| Target-native internal tasks | Covers work owned and managed "
            "by the target under its local workflow. |",
        ):
            self.assertIn(hint_row, discovery)

    @requires_documentation_repository
    def test_research_process_separates_local_and_external_checkpoints(self):
        process = read_repository_file(
            "processes/research-and-discovery-planning.md"
        )

        for required_text in (
            "method",
            "observations",
            "produced artifacts",
            "limitations",
            "next action",
            "local Evidence Workspace",
            "external result remains `pending`",
            "Return Channel",
        ):
            self.assertIn(required_text, process)

    @requires_documentation_repository
    def test_handoff_wikilinks_resolve_to_files_and_headings(self):
        for relative_path in (
            "AGENTS.md",
            "handbook/README.md",
            "handbook/architecture-to-openspec-handoff.md",
            "processes/architecture-to-openspec-handoff.md",
            "tools/architecture_handoff/README.md",
            "tools/architecture_handoff/design/README.md",
            "tools/architecture_handoff/design/query-contract.md",
            "tools/architecture_handoff/design/github-adapter.md",
            "tools/architecture_handoff/design/workflows-and-safety.md",
            "tools/architecture_handoff/design/write-coordinator.md",
        ):
            document = read_repository_file(relative_path)
            raw_targets = re.findall(
                r"\[\[([^]|]+)(?:\|[^]]+)?\]\]",
                document,
            )
            for raw_target in raw_targets:
                target, separator, heading = raw_target.partition("#")
                target_path = REPOSITORY_ROOT / target
                if target_path.suffix != ".md":
                    target_path = target_path.with_suffix(".md")
                self.assertTrue(
                    target_path.is_file(),
                    f"{relative_path}: missing wikilink target {target}",
                )
                if separator:
                    target_document = target_path.read_text(encoding="utf-8")
                    self.assertRegex(
                        target_document,
                        rf"(?m)^#+ {re.escape(heading)}$",
                        f"{relative_path}: missing heading {raw_target}",
                    )

    @requires_documentation_repository
    def test_handoff_documentation_navigation_preserves_authority(self):
        process = read_repository_file(
            "processes/architecture-to-openspec-handoff.md"
        )
        handbook = read_repository_file(
            "handbook/architecture-to-openspec-handoff.md"
        )
        package = read_repository_file("tools/architecture_handoff/README.md")

        self.assertIn(
            "[[handbook/architecture-to-openspec-handoff|",
            process,
        )
        self.assertNotIn("[[tools/architecture_handoff/", process)
        self.assertIn(
            "[[processes/architecture-to-openspec-handoff|",
            handbook,
        )
        self.assertIn("[[tools/architecture_handoff/README|", handbook)
        self.assertIn(
            "[[processes/architecture-to-openspec-handoff|",
            package,
        )
        self.assertIn(
            "[[handbook/architecture-to-openspec-handoff|",
            package,
        )

    def test_handoff_designs_live_with_owning_package(self):
        for obsolete_root_design in (
            "architecture-to-openspec-handoff-advanced-search-design.md",
            "architecture-to-openspec-handoff-p1-write-coordinator-design.md",
        ):
            self.assertFalse(
                (REPOSITORY_ROOT / obsolete_root_design).exists()
            )

        for package_design in (
            "README.md",
            "github-adapter.md",
            "query-contract.md",
            "workflows-and-safety.md",
            "write-coordinator.md",
        ):
            self.assertTrue(
                (
                    REPOSITORY_ROOT
                    / "tools/architecture_handoff/design"
                    / package_design
                ).is_file()
            )

    def test_handoff_cleanup_has_durable_owners(self):
        for completed_plan in (
            "architecture-to-openspec-handoff-p0-implementation-plan.md",
            "architecture-to-openspec-handoff-p1-implementation-plan.md",
            "architecture-to-openspec-handoff-advanced-search-implementation-plan.md",
        ):
            self.assertFalse((REPOSITORY_ROOT / completed_plan).exists())

        package = read_repository_file("tools/architecture_handoff/README.md")
        design = read_repository_file(
            "tools/architecture_handoff/design/README.md"
        )
        workflows = read_repository_file(
            "tools/architecture_handoff/design/workflows-and-safety.md"
        )
        github_design = read_repository_file(
            "tools/architecture_handoff/design/github-adapter.md"
        )
        temporary_validation = (
            REPOSITORY_ROOT
            / "architecture-to-openspec-handoff-exclusions-and-unverified-work.md"
        )
        compact_package = " ".join(package.split())

        self.assertIn(
            "currently ships one provider adapter: GitHub Issues",
            package,
        )
        for future_adapter_boundary in (
            "GitLab",
            "Jira",
            "Markdown",
            "other adapter",
            "only when a real target needs it",
            "separate provider mapping",
            "conformance scope",
        ):
            self.assertIn(future_adapter_boundary, compact_package)

        self.assertIn(
            "## Current Design Constraints and Non-Goals",
            design,
        )
        self.assertNotIn("- New GitLab, Jira, or Markdown adapters.", design)
        for rejected_mechanism in (
            "persisted workflow engine",
            "repository-local search index",
            "Background synchronization",
            "Adapter-side scans",
            "Local embeddings",
            "unattended routing",
            "Automatic migration",
            "Stable identifiers for arc42",
        ):
            self.assertIn(rejected_mechanism, design)

        self.assertNotIn("Live Validation Status", github_design)
        self.assertFalse(temporary_validation.exists())
        for current_guidance in (
            package,
            design,
            workflows,
            github_design,
        ):
            self.assertNotIn(
                "architecture-to-openspec-handoff-exclusions-and-unverified-work",
                current_guidance,
            )
        self.assertIn("fake transports", workflows)
        self.assertIn("separate exact-target", workflows)
        self.assertIn("exact-payload", workflows)
        self.assertIn("cleanup-or-retention approval", workflows)
if __name__ == "__main__":
    unittest.main()
