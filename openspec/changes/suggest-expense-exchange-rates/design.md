## Context

`record-project-expenses` plans exact manual conversion and reserves provider,
observation-date, and adjustment provenance on each Expense. The current Tauri
shell has no HTTP capability or client dependency. ECB publishes daily EXR
reference observations with EUR as the base and does not provide every ISO
currency or every calendar date. See `proposal.md` and the Expense delta spec
for the approved behavior.

## Goals / Non-Goals

**Goals:**

- Put network, ECB response validation, historical observation selection, and
  direction normalization behind one small provider interface.
- Keep Client, Project, description, and amount data out of external requests.
- Reuse the base Expense money conversion and persistence behavior after a
  suggestion is returned.
- Make every provider failure recoverable without weakening manual conversion.

**Non-Goals:**

- Build a pluggable provider marketplace, background refresh daemon, or market
  execution-rate feed.
- Cache or silently reuse suggestions across Expenses.
- Add OAuth, provider credentials, analytics, or telemetry.

## Decisions

### Fetch ECB data through one native command

Add `src-tauri/src/exchange_rates.rs` and expose one command that accepts
validated `YYYY-MM-DD`, original currency code, and billing currency code. The
native module uses a narrowly configured HTTPS client to call the ECB Data API
for daily EXR reference observations ending on the requested date. It validates
status, content type, series identity, observation dates, and positive decimal
values before returning a suggestion.

The module keeps an internal transport seam so deterministic Rust tests can use
fixtures for success, missing dates, malformed responses, timeouts, and status
errors. The production adapter is the only code that learns the ECB endpoint.
The public Tauri command returns `{ provider, observedOn, rate }` in the
canonical pair direction.

Calling ECB from the webview was rejected because browser CORS and platform
webview differences would widen the interface and tests. A general Tauri HTTP
plugin was rejected because one native command needs less permission surface.

### Select one shared observation date before calculating a cross-rate

ECB observations mean `1 EUR = quote currency units`. For a source `S` and
billing currency `B`, the provider computes `B_per_EUR / S_per_EUR`, treating
EUR's quote as exactly `1`. It selects the latest observation date on or before
the Expense date for which every required non-EUR series is present. Reversing
the pair therefore recomputes the reciprocal direction rather than reusing a
previous result.

Parse positive decimal observations as exact scaled integers, calculate the
ratio with enough intermediate precision, and emit a canonical decimal string
with at most the base Expense limit of 12 fractional digits. Half-up rounding
at the rate boundary is separate from the later half-up money rounding.

Independently taking each currency's latest observation was rejected because
two different publication dates could create a synthetic cross-rate the user
did not request.

### Keep the frontend provider interface small

Add `ExpenseRateProvider.suggest(command)` returning a typed `RateSuggestion`
and a `TauriExpenseRateProvider` adapter that invokes the native command.
`ExpenseForm` owns transient idle/loading/success/error state. `Get rate` is the
only trigger. Success passes the returned rate through the existing exact money
module to preview billing amount; failure leaves the draft untouched.

An in-memory adapter and shared contract cover the frontend interface. The page
does not know the ECB URL, quote base, response format, or native error strings.

Exposing raw ECB series to the form was rejected because it would leak provider
direction rules into every caller.

### Preserve suggestion provenance through manual adjustment

The base Expense schema records `rate_source`, nullable `rate_observed_on`, and
`rate_manually_adjusted`. A manual-only conversion uses `manual`, no observation
date, and false. Applying an ECB suggestion uses `ECB`, the selected observation
date, and false. Editing either the rate or final billing amount afterward keeps
the ECB source/date and flips the adjustment flag to true.

The form labels ECB values as reference suggestions for information. Saved rows
can display the source and date without claiming the value was a market
transaction rate.

Replacing source provenance with `manual` after an edit was rejected because it
would hide which reference informed the user's final value.

### Translate native failures into stable recovery states

Define stable error codes for unavailable network, unsupported currency,
missing observation, invalid provider data, and generic provider failure. The
TypeScript adapter maps them to sentence-case copy and Retry while retaining the
manual fields. Native responses and URLs are not shown to the user.

Automatic fallback to an unapproved provider was rejected because it would
change the privacy and reference-rate semantics without user consent.

## Risks / Trade-offs

- **ECB changes its response schema or series identifiers** → Validate every
  response and fail closed to manual conversion using fixture contract tests.
- **A currency is valid in `Intl` but absent from ECB** → Return unsupported and
  keep manual entry enabled.
- **Two series have different latest dates** → Intersect observation dates and
  choose one shared date only.
- **A very small inverse rate loses meaningful digits** → Calculate with exact
  scaled integers and retain up to 12 fractional digits before money rounding.
- **A network request hangs** → Configure bounded connect/request timeouts and
  keep Retry explicit.

## Migration Plan

1. Add the provider interface and in-memory contract before native integration.
2. Implement and fixture-test ECB observation selection and normalization in
   Rust, then register the narrow Tauri command and HTTPS dependency.
3. Integrate explicit request state into ExpenseForm and provenance into the
   existing Expense command without adding a second conversion path.
4. Roll back by removing command wiring and UI access; saved provenance and
   manually usable Expenses remain valid.
