## ADDED Requirements

### Requirement: Request an Expense rate explicitly
The application SHALL offer `Get rate` only when an Expense's original currency
differs from its saved Client billing currency. It SHALL contact the external
provider only after the user activates that control and SHALL send only the
requested currencies and Expense date, not the Client, Project, description, or
amount.

#### Scenario: Request a suggested rate
- **WHEN** the user activates `Get rate` for a different-currency Expense
- **THEN** the application requests a suggestion for that Expense date and exact original-to-billing currency pair

#### Scenario: Do not request automatically
- **WHEN** the user opens or edits a different-currency Expense without activating `Get rate`
- **THEN** the application performs no exchange-rate network request

#### Scenario: Keep same-currency conversion local
- **WHEN** the original currency matches the Client billing currency
- **THEN** the application keeps the rate at `1` and does not offer `Get rate`

### Requirement: Resolve an ECB observation for the Expense date
The application SHALL use ECB reference-rate observations as its default
suggestion source. It SHALL use the Expense date when an observation exists for
that date; otherwise it SHALL use the latest published observation earlier than
the Expense date and expose the actual observation date used.

#### Scenario: Use an exact-date observation
- **WHEN** ECB publishes the required observations for the Expense date
- **THEN** the application uses that date and identifies it as the observation date

#### Scenario: Fall back across a non-publishing day
- **WHEN** the Expense date is a weekend or other date without the required ECB observation
- **THEN** the application uses the latest earlier date on which all required observations are available and displays that date

#### Scenario: No prior observation is available
- **WHEN** no usable earlier ECB observation exists for the requested currencies
- **THEN** the application leaves the current conversion draft unchanged and explains that the rate must be entered manually

### Requirement: Normalize every suggested pair direction
The application SHALL present and apply every suggestion in the canonical
direction `1 original currency = X Client billing currency`. It SHALL correctly
derive direct, inverse, and non-EUR cross-rates from ECB observations whose base
is EUR.

#### Scenario: Convert from EUR
- **WHEN** the original currency is EUR and the Client billing currency is supported by ECB
- **THEN** the application uses the published units of billing currency per EUR as the canonical rate

#### Scenario: Convert to EUR
- **WHEN** the Client billing currency is EUR and the original currency is supported by ECB
- **THEN** the application uses the inverse of the published units of original currency per EUR

#### Scenario: Calculate a non-EUR cross-rate
- **WHEN** both currencies are supported non-EUR currencies
- **THEN** the application divides their EUR-based observations in the order required to produce billing currency per one original currency

#### Scenario: Reverse a currency pair
- **WHEN** the user swaps original and Client billing currencies
- **THEN** a new request uses the reversed canonical direction instead of reusing the previous pair's rate

### Requirement: Apply a non-authoritative suggestion
After a successful request, the application SHALL populate the applied rate and
recalculate the billing-amount preview using the existing exact conversion and
rounding rules. It SHALL identify the value as an ECB reference-rate suggestion
for information and SHALL keep both the rate and final billing amount editable.

#### Scenario: Accept the suggested rate unchanged
- **WHEN** the user saves after receiving a suggestion without editing the conversion
- **THEN** the Expense retains `ECB`, the actual observation date, the applied rate, and both authoritative amounts

#### Scenario: Adjust the suggested rate
- **WHEN** the user edits a suggested applied rate before saving
- **THEN** the application recalculates the billing amount and marks the final conversion as manually adjusted while retaining the suggestion's source and observation date

#### Scenario: Enter a rounded billing amount after a suggestion
- **WHEN** the user edits the final billing amount after receiving a suggestion
- **THEN** the application derives the applied rate, preserves that exact billing amount, and marks the conversion as manually adjusted

### Requirement: Preserve manual conversion when suggestion fails
A failed, malformed, unsupported, or unavailable ECB response SHALL NOT clear
the user's current conversion draft or prevent manual Expense conversion. The
application SHALL provide a recoverable error and allow Retry.

#### Scenario: Network request fails
- **WHEN** the ECB request cannot be completed
- **THEN** the current rate and billing amount remain unchanged and the application offers Retry or continued manual entry

#### Scenario: Provider response is malformed
- **WHEN** returned data cannot be validated as the requested observations
- **THEN** the application does not apply it and explains that the rate must be retried or entered manually

#### Scenario: Currency is unsupported by ECB
- **WHEN** either currency has no usable ECB reference series
- **THEN** the application identifies that no suggestion is available and leaves manual conversion enabled
