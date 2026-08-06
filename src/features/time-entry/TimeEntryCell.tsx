import { useEffect, useId, useRef } from "react";

import { Input } from "@/components/ui/input";

export interface TimeEntryCellProps {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly onCommit: (value: string) => void;
  readonly onEscape: () => void;
  readonly validationError?: string;
  readonly saveError?: string;
  readonly readOnly?: boolean;
  readonly focusRequest?: number;
}

export function TimeEntryCell({
  label,
  value,
  onChange,
  onCommit,
  onEscape,
  validationError,
  saveError,
  readOnly = false,
  focusRequest,
}: TimeEntryCellProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const previousFocusRequest = useRef(focusRequest);
  const errorId = useId();
  const error = saveError ?? validationError;

  useEffect(() => {
    if (previousFocusRequest.current !== focusRequest) {
      inputRef.current?.focus();
      previousFocusRequest.current = focusRequest;
    }
  }, [focusRequest]);

  return (
    <div className="grid min-w-[4.75rem] gap-1">
      <Input
        aria-describedby={error ? errorId : undefined}
        aria-invalid={Boolean(error)}
        aria-label={label}
        autoComplete="off"
        className="h-8 px-2 text-right font-mono text-sm tabular-nums"
        inputMode="numeric"
        onBlur={() => {
          if (!readOnly) onCommit(value);
        }}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (readOnly) return;
          if (event.key === "Enter") {
            event.preventDefault();
            onCommit(value);
          } else if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            onEscape();
          }
        }}
        placeholder="H:MM"
        readOnly={readOnly}
        ref={inputRef}
        spellCheck={false}
        value={value}
      />
      {saveError ? (
        <p
          className="text-xs leading-4 text-destructive"
          id={errorId}
          role="alert"
        >
          {saveError}
        </p>
      ) : validationError ? (
        <span className="sr-only" id={errorId}>
          {validationError}
        </span>
      ) : null}
    </div>
  );
}
