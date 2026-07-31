# Personal Timesheet

Personal Timesheet describes billable work and related costs for a single
person working across multiple clients.

## Language

**Client**:
A person or organization for whom work is performed and billed.
_Avoid_: Customer, account

**Active client**:
A client currently available for new work and time entry.

**Archived client**:
A retained client no longer shown among active choices for new work.
_Avoid_: Deleted client

**Billing currency**:
The currency in which a client's time and expenses are valued.
_Avoid_: Default currency

**Default hourly rate**:
The client-level price for one hour of work, inherited by later work items
unless they define an override.
_Avoid_: Client rate, base rate

**Project**:
A named body of work performed for exactly one client and available for direct
time entry or further division into tasks.

**Inherited hourly rate**:
An hourly rate obtained from the nearest ancestor that defines one rather than
entered on the current project or task.
_Avoid_: Copied rate, defaulted rate

**Hourly rate override**:
An explicit non-negative hourly rate defined on a project or task instead of
its inherited rate; zero is a valid override.
_Avoid_: Custom rate

**Effective hourly rate**:
The rate that applies after resolving overrides from task to project to client;
it remains unset when no level defines one.
_Avoid_: Final rate, resolved rate
