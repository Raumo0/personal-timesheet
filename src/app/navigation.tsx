import {
  CalendarDays,
  ChartNoAxesCombined,
  ReceiptText,
  Settings2,
  type LucideIcon,
} from "lucide-react";

export type WorkspaceDensity = "compact" | "comfortable";

export type NavigationDestination = {
  path: string;
  label: string;
  description: string;
  emptyState: string;
  density: WorkspaceDensity;
  icon: LucideIcon;
};

export const navigationDestinations: NavigationDestination[] = [
  {
    path: "/",
    label: "Timesheet",
    description: "Plan your week and record time without losing context.",
    emptyState: "Your weekly time entries will appear here.",
    density: "compact",
    icon: CalendarDays,
  },
  {
    path: "/reports",
    label: "Reports",
    description: "Understand where your time and billable value are going.",
    emptyState: "Reports will appear as soon as you record time.",
    density: "comfortable",
    icon: ChartNoAxesCombined,
  },
  {
    path: "/expenses",
    label: "Expenses",
    description: "Keep reimbursable costs together with client work.",
    emptyState: "Your project expenses will appear here.",
    density: "comfortable",
    icon: ReceiptText,
  },
  {
    path: "/settings",
    label: "Settings",
    description: "Manage the workspace defaults that support your workflow.",
    emptyState: "Workspace preferences will be available here.",
    density: "comfortable",
    icon: Settings2,
  },
];
