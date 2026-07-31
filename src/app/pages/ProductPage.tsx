import type { NavigationDestination } from "@/app/navigation";

export function ProductPage({
  destination,
}: {
  destination: NavigationDestination;
}) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="max-w-3xl">
        <h1 className="text-balance text-2xl font-semibold tracking-tight text-foreground">
          {destination.label}
        </h1>
        <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
          {destination.description}
        </p>
      </header>

      <section
        aria-label={`${destination.label} workspace`}
        className="mt-6 flex min-h-72 flex-1 items-center justify-center rounded-xl border border-dashed bg-card/60 p-8 shadow-xs"
      >
        <div className="max-w-sm text-center">
          <destination.icon
            aria-hidden="true"
            className="mx-auto size-8 text-primary"
            strokeWidth={1.6}
          />
          <p className="mt-4 text-sm font-medium text-foreground">
            {destination.emptyState}
          </p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            This area is ready for the next focused product slice.
          </p>
        </div>
      </section>
    </div>
  );
}
