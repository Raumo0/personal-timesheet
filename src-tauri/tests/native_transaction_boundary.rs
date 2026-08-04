mod support;

use personal_timesheet_lib::catalog_lifecycle::{
    apply_at_path as apply_lifecycle_at_path, LifecyclePlan,
};
use personal_timesheet_lib::client_update::{apply_at_path, ClientUpdatePlan};
use serde_json::json;
use support::CatalogFixture;

fn plan() -> ClientUpdatePlan {
    serde_json::from_value(json!({
        "clientId": "client-1",
        "expectedClient": {
            "id": "client-1", "name": "Acme", "normalizedName": "acme",
            "currencyCode": "EUR", "hourlyRateMinor": 12500,
            "createdAt": "2026-07-30T08:00:00.000Z",
            "updatedAt": "2026-07-31T09:00:00.000Z", "archivedAt": null
        },
        "client": {
            "id": "client-1", "name": "Acme Consulting", "normalizedName": "acme consulting",
            "currencyCode": "JPY", "hourlyRateMinor": 125,
            "createdAt": "2026-07-30T08:00:00.000Z",
            "updatedAt": "2026-08-04T10:15:00.000Z", "archivedAt": null
        },
        "overrides": [
            { "kind": "project", "id": "project-1", "expectedHourlyRateOverrideMinor": 12500, "expectedUpdatedAt": "old", "hourlyRateOverrideMinor": 125 },
            { "kind": "task", "id": "task-1", "expectedHourlyRateOverrideMinor": 7500, "expectedUpdatedAt": "old", "hourlyRateOverrideMinor": 75 }
        ],
        "updatedAt": "2026-08-04T10:15:00.000Z"
    }))
    .expect("fixture plan should deserialize")
}

fn lifecycle_plan() -> LifecyclePlan {
    serde_json::from_value(json!({
        "operation": "archive",
        "target": { "kind": "client", "id": "client-1" },
        "records": [
            { "kind": "client", "id": "client-1", "name": "Acme", "archivedAt": null },
            { "kind": "project", "id": "project-1", "name": "Website", "archivedAt": null },
            { "kind": "project", "id": "project-null", "name": "Internal", "archivedAt": null },
            { "kind": "task", "id": "task-1", "name": "Research", "archivedAt": null },
            { "kind": "task", "id": "task-null", "name": "Coordination", "archivedAt": null }
        ],
        "impactDescription": "Archive Acme and every Project and Task beneath it (2 Projects, 2 Tasks)."
    }))
    .expect("lifecycle fixture plan should deserialize")
}

#[test]
fn commits_client_project_and_task_when_commit_is_accidentally_omitted() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        apply_at_path(&fixture.path, plan())
            .await
            .expect("valid plan should commit");

        let state = fixture.state().await;
        assert_eq!(
            state.client,
            (
                "Acme Consulting".into(),
                "JPY".into(),
                125,
                "2026-08-04T10:15:00.000Z".into()
            )
        );
        assert_eq!(
            state.projects,
            vec![
                (
                    "project-1".into(),
                    Some(125),
                    "2026-08-04T10:15:00.000Z".into()
                ),
                ("project-null".into(), None, "old".into())
            ]
        );
        assert_eq!(
            state.tasks,
            vec![
                ("task-1".into(), Some(75), "2026-08-04T10:15:00.000Z".into()),
                ("task-null".into(), None, "old".into())
            ]
        );
    });
}

#[test]
fn rolls_back_client_and_project_when_an_intermediate_task_update_fails() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        let before = fixture.state().await;
        fixture.execute("CREATE TRIGGER fail_task_update BEFORE UPDATE ON tasks WHEN OLD.id = 'task-1' BEGIN SELECT RAISE(ABORT, 'task update failed'); END;").await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("task failure should reject the plan");
        assert!(error.contains("task update failed"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn writes_nothing_when_the_expected_client_snapshot_is_stale() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture
            .execute("UPDATE clients SET name = 'Changed elsewhere' WHERE id = 'client-1'")
            .await;
        let before = fixture.state().await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("stale client should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn writes_nothing_when_an_expected_override_snapshot_is_stale() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture
            .execute("UPDATE tasks SET hourly_rate_override_minor = 7600 WHERE id = 'task-1'")
            .await;
        let before = fixture.state().await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("stale override should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn writes_nothing_when_a_project_updated_at_snapshot_is_stale() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture.execute("UPDATE projects SET updated_at = 'changed' WHERE id = 'project-1'").await;
        let before = fixture.state().await;
        let error = apply_at_path(&fixture.path, plan()).await.expect_err("stale project timestamp should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn writes_nothing_when_a_task_updated_at_snapshot_is_stale() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture.execute("UPDATE tasks SET updated_at = 'changed' WHERE id = 'task-1'").await;
        let before = fixture.state().await;
        let error = apply_at_path(&fixture.path, plan()).await.expect_err("stale task timestamp should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn writes_nothing_when_a_planned_project_or_task_is_archived() {
    tauri::async_runtime::block_on(async {
        for (table, id) in [("projects", "project-1"), ("tasks", "task-1")] {
            let fixture = CatalogFixture::new().await;
            fixture
                .execute(&format!(
                    "UPDATE {table} SET archived_at = '2026-08-04T10:00:00.000Z' WHERE id = '{id}'"
                ))
                .await;
            let before = fixture.state().await;

            let error = apply_at_path(&fixture.path, plan())
                .await
                .expect_err("archived planned descendant should reject the plan");
            assert!(error.contains("stale-plan"), "{table}: {error}");
            assert_eq!(
                fixture.state().await,
                before,
                "{table} writes must stay zero"
            );
        }
    });
}

#[test]
fn writes_nothing_when_an_expected_descendant_is_missing() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture
            .execute("DELETE FROM tasks WHERE id = 'task-1'")
            .await;
        let before = fixture.state().await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("missing task should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn writes_nothing_when_an_unexpected_non_null_descendant_is_added() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture.execute("INSERT INTO tasks VALUES ('task-added', 'project-1', 'Added', 'added', 9000, 'created', 'old', NULL)").await;
        let before = fixture.state().await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("unexpected task should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn rolls_back_every_write_when_an_override_row_count_is_not_one() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        let before = fixture.state().await;
        fixture.execute("CREATE TRIGGER ignore_task_update BEFORE UPDATE ON tasks WHEN OLD.id = 'task-1' BEGIN SELECT RAISE(IGNORE); END;").await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("zero updated rows should reject the plan");
        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn preserves_primary_and_rollback_failures_when_a_trigger_aborts_the_transaction() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        let before = fixture.state().await;
        fixture.execute("CREATE TRIGGER rollback_task_update BEFORE UPDATE ON tasks WHEN OLD.id = 'task-1' BEGIN SELECT RAISE(ROLLBACK, 'primary task failure'); END;").await;

        let error = apply_at_path(&fixture.path, plan())
            .await
            .expect_err("trigger should abort apply and its explicit rollback");
        assert!(error.contains("primary task failure"), "{error}");
        assert!(error.contains("rollback"), "{error}");
        assert_eq!(fixture.state().await, before);
    });
}

#[test]
fn lifecycle_writes_nothing_when_descendant_snapshot_recheck_is_omitted() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        fixture
            .execute("UPDATE tasks SET name = 'Changed elsewhere' WHERE id = 'task-1'")
            .await;
        let before = fixture.lifecycle_state().await;

        let error = apply_lifecycle_at_path(&fixture.path, lifecycle_plan())
            .await
            .expect_err("stale lifecycle hierarchy should reject the plan");

        assert!(error.contains("stale-plan"), "{error}");
        assert_eq!(fixture.lifecycle_state().await, before);
    });
}

#[test]
fn lifecycle_rolls_back_ancestor_updates_when_intermediate_task_update_fails() {
    tauri::async_runtime::block_on(async {
        let fixture = CatalogFixture::new().await;
        let before = fixture.lifecycle_state().await;
        fixture.execute("CREATE TRIGGER fail_lifecycle_task_update BEFORE UPDATE OF archived_at ON tasks WHEN OLD.id = 'task-1' BEGIN SELECT RAISE(ABORT, 'lifecycle task update failed'); END;").await;

        let error = apply_lifecycle_at_path(&fixture.path, lifecycle_plan())
            .await
            .expect_err("intermediate lifecycle update should roll back");

        assert!(error.contains("lifecycle task update failed"), "{error}");
        assert_eq!(fixture.lifecycle_state().await, before);
    });
}
