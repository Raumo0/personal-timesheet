import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { rowKey, type WorkReference } from "./weekly-time-entry";
import type { SelectableWork } from "./weekly-time-entry-store";

export interface WorkItemSelectorProps {
  readonly work: readonly SelectableWork[];
  readonly existingRowKeys: ReadonlySet<string>;
  readonly onSelect: (reference: WorkReference) => void;
  readonly onRequestFocus: (rowKey: string) => void;
}

export function WorkItemSelector({
  work,
  existingRowKeys,
  onSelect,
  onRequestFocus,
}: WorkItemSelectorProps) {
  const references = new Map<string, WorkReference>();
  for (const client of work) {
    for (const { project, tasks } of client.projects) {
      const projectReference: WorkReference = {
        kind: "project",
        projectId: project.id,
      };
      references.set(rowKey(projectReference), projectReference);
      for (const task of tasks) {
        const taskReference: WorkReference = { kind: "task", taskId: task.id };
        references.set(rowKey(taskReference), taskReference);
      }
    }
  }

  function choose(value: string | null) {
    if (!value) return;
    const reference = references.get(value);
    if (!reference) return;
    const key = rowKey(reference);
    if (existingRowKeys.has(key)) {
      onRequestFocus(key);
    } else {
      onSelect(reference);
    }
  }

  return (
    <Select disabled={references.size === 0} onValueChange={choose} value={null}>
      <SelectTrigger
        aria-label="Select project or task"
        className="w-64 max-w-full"
      >
        <SelectValue placeholder="Select project or task" />
      </SelectTrigger>
      <SelectContent
        align="start"
        alignItemWithTrigger={false}
        className="min-w-64"
      >
        {work.map(({ client, projects }) => (
          <SelectGroup key={client.id}>
            <SelectLabel>{client.name}</SelectLabel>
            {projects.flatMap(({ project, tasks }) => {
              const projectValue = rowKey({
                kind: "project",
                projectId: project.id,
              });
              const projectExists = existingRowKeys.has(projectValue);
              return [
                <SelectItem
                  aria-label={projectExists ? `Project · ${project.name} Already added` : undefined}
                  className={projectExists ? "bg-muted/60 font-medium" : "font-medium"}
                  key={projectValue}
                  value={projectValue}
                >
                  <span className="flex w-full items-center justify-between gap-3">
                    <span>Project · {project.name}</span>
                    {projectExists ? (
                      <span className="text-xs text-muted-foreground">Already added</span>
                    ) : null}
                  </span>
                </SelectItem>,
                ...tasks.map((task) => {
                  const taskValue = rowKey({ kind: "task", taskId: task.id });
                  const taskExists = existingRowKeys.has(taskValue);
                  return (
                    <SelectItem
                      aria-label={taskExists ? `Task · ${task.name} Already added` : undefined}
                      className={taskExists ? "bg-muted/60 pl-5" : "pl-5"}
                      key={taskValue}
                      value={taskValue}
                    >
                      <span className="flex w-full items-center justify-between gap-3">
                        <span>Task · {task.name}</span>
                        {taskExists ? (
                          <span className="text-xs text-muted-foreground">Already added</span>
                        ) : null}
                      </span>
                    </SelectItem>
                  );
                }),
              ];
            })}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
