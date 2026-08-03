## Why

Manual conversion makes multi-currency Expenses usable but forces the user to
find and transpose historical rates independently. An explicit, non-authoritative
ECB suggestion can reduce errors while preserving the user's final control.

## What Changes

- Add `Get rate` to a different-currency Expense conversion without performing
  any automatic or background network request.
- Request ECB reference data for the Expense date and currency pair, using the
  latest earlier published observation for a weekend or TARGET closing day.
- Normalize ECB's EUR-based observations to
  `1 original currency = X Client billing currency`, including correct
  inversion and cross-rate calculation for either pair direction.
- Populate the applied rate and billing-amount preview while keeping both fields
  manually editable before save.
- Save `ECB`, the actual observation date, and the final applied rate as
  provenance; a later manual edit remains visibly distinguishable from the
  original suggestion.
- Keep manual conversion available when the network, date, or currency pair is
  unavailable and explain that ECB reference rates are informational.
- Defer automatic refresh, live-market execution rates, alternate providers,
  recurring Expense generation, reports, invoices, and payments.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `expense-recording`: Adds explicit ECB rate suggestions, historical fallback,
  pair-direction normalization, manual fallback, and saved provenance to the
  existing manual conversion flow.

## Impact

- Extends the Expense form and saved conversion provenance planned by
  `record-project-expenses`; that change must be implemented first.
- Adds one narrow native exchange-rate command, an ECB provider adapter, and
  the minimum HTTPS client dependency required by the Rust shell.
- Sends only the requested date and currency pair to the provider; Client,
  Project, description, and amount remain local.
- Adds no database migration when the base Expense schema reserves nullable
  provider and observation-date provenance columns; otherwise implementation
  adds the next additive migration without rewriting saved Expenses.
