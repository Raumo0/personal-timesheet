import { Check, Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import { useTheme, type Appearance } from "./ThemeProvider";

const options: Array<{
  value: Appearance;
  label: string;
  icon: typeof Monitor;
}> = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function ThemeMenu() {
  const { appearance, setAppearance } = useTheme();
  const selected = options.find((option) => option.value === appearance)!;
  const SelectedIcon = selected.icon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            aria-label={`Appearance: ${selected.label}`}
            size="icon"
            variant="ghost"
          >
            <SelectedIcon aria-hidden="true" />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Appearance</DropdownMenuLabel>
          {options.map((option) => {
            const Icon = option.icon;
            const isSelected = option.value === appearance;

            return (
              <DropdownMenuItem
                key={option.value}
                onClick={() => setAppearance(option.value)}
              >
                <Icon aria-hidden="true" />
                <span>{option.label}</span>
                <Check
                  aria-hidden="true"
                  className={cn("ml-auto", !isSelected && "invisible")}
                />
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
