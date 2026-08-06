export interface FixedScaleRate {
  coefficient: bigint;
  scale: number;
}

const MAX_SAFE_MINOR = BigInt(Number.MAX_SAFE_INTEGER);

function assertSupportedCurrency(currencyCode: string): void {
  const supported = (
    Intl as typeof Intl & { supportedValuesOf(key: "currency"): string[] }
  ).supportedValuesOf("currency");
  if (!/^[A-Z]{3}$/.test(currencyCode) || !supported.includes(currencyCode)) {
    throw new Error("Choose a supported currency");
  }
}

function assertSafeMinorUnits(minorUnits: number): void {
  if (!Number.isSafeInteger(minorUnits) || minorUnits < 0) {
    throw new Error("Money amount must be non-negative safe minor units");
  }
}

export function currencyFractionDigits(currencyCode: string): number {
  assertSupportedCurrency(currencyCode);
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency: currencyCode,
  }).resolvedOptions().maximumFractionDigits ?? 2;
}

export function parseMinorUnits(rawValue: string, currencyCode: string): number {
  const fractionDigits = currencyFractionDigits(currencyCode);
  const normalized = rawValue.trim().includes(".")
    ? rawValue.trim()
    : rawValue.trim().replace(",", ".");
  const match = normalized.match(/^(\d+)(?:\.(\d+))?$/);
  if (!match || (match[2]?.length ?? 0) > fractionDigits) {
    throw new Error(`Enter a non-negative amount with up to ${fractionDigits} decimals`);
  }

  const minorUnits = BigInt(
    `${match[1]}${(match[2] ?? "").padEnd(fractionDigits, "0")}`,
  );
  if (minorUnits > MAX_SAFE_MINOR) {
    throw new Error("Money amount is too large");
  }
  return Number(minorUnits);
}

export function formatMinorUnits(
  minorUnits: number,
  currencyCode: string,
  locale?: string,
): string {
  assertSafeMinorUnits(minorUnits);
  const fractionDigits = currencyFractionDigits(currencyCode);
  const divisor = 10n ** BigInt(fractionDigits);
  const value = BigInt(minorUnits);
  const whole = value / divisor;
  const fraction = (value % divisor).toString().padStart(fractionDigits, "0");
  const formatter = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currencyCode,
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });

  return formatter
    .formatToParts(whole)
    .map((part) => (part.type === "fraction" ? fraction : part.value))
    .join("");
}

export function parseFixedScaleRate(rawValue: string): FixedScaleRate {
  const value = rawValue.trim();
  const match = value.match(/^(\d+)(?:\.(\d{1,12}))?$/);
  if (!match) {
    throw new Error("Enter a positive rate with up to 12 decimals");
  }

  const fraction = match[2] ?? "";
  const coefficient = BigInt(`${match[1]}${fraction}`);
  if (coefficient <= 0n) {
    throw new Error("Exchange rate must be positive");
  }
  return { coefficient, scale: fraction.length };
}

export function convertMinorUnits(
  minorUnits: number,
  sourceCurrencyCode: string,
  targetCurrencyCode: string,
  rawRate: string,
): number {
  assertSafeMinorUnits(minorUnits);
  const sourceDigits = currencyFractionDigits(sourceCurrencyCode);
  const targetDigits = currencyFractionDigits(targetCurrencyCode);
  const rate = parseFixedScaleRate(rawRate);
  const numerator =
    BigInt(minorUnits) * rate.coefficient * 10n ** BigInt(targetDigits);
  const denominator = 10n ** BigInt(sourceDigits + rate.scale);
  const quotient = numerator / denominator;
  const remainder = numerator % denominator;
  const rounded = quotient + (remainder * 2n >= denominator ? 1n : 0n);
  if (rounded > MAX_SAFE_MINOR) {
    throw new Error("Converted money amount is too large");
  }
  return Number(rounded);
}

export function rescaleMinorUnits(
  minorUnits: number,
  fromCurrencyCode: string,
  toCurrencyCode: string,
): number {
  assertSafeMinorUnits(minorUnits);
  const difference =
    currencyFractionDigits(toCurrencyCode) -
    currencyFractionDigits(fromCurrencyCode);
  if (difference === 0) return minorUnits;

  if (difference > 0) {
    const result = BigInt(minorUnits) * 10n ** BigInt(difference);
    if (result > MAX_SAFE_MINOR) {
      throw new Error("Money amount is too large for the new currency");
    }
    return Number(result);
  }

  const divisor = 10n ** BigInt(-difference);
  if (BigInt(minorUnits) % divisor !== 0n) {
    throw new Error("Money amount cannot be represented in the new currency");
  }
  return Number(BigInt(minorUnits) / divisor);
}
