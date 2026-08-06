import { createRoot } from "react-dom/client";

import { InvoicePreview } from "../InvoicePreview";
import { invoiceValidationDocument } from "./documents";
import "./preview.css";

const validationWindow = window as typeof window & {
  __INVOICE_PREVIEW_VALIDATION__?: { caseName: string; width: number };
};
const parameters = new URLSearchParams(window.location.search);
const caseName =
  validationWindow.__INVOICE_PREVIEW_VALIDATION__?.caseName ??
  parameters.get("case") ??
  "both-charts";
const width =
  validationWindow.__INVOICE_PREVIEW_VALIDATION__?.width ??
  Number(parameters.get("width") ?? 1120);
const root = document.getElementById("root");

if (!root || !Number.isInteger(width) || width < 320 || width > 1200) {
  throw new Error("Invalid invoice preview validation parameters");
}

createRoot(root).render(
  <div className="validation-preview-shell">
    <div
      className="validation-preview-frame"
      data-validation-case={caseName}
      style={{ width }}
    >
      <InvoicePreview document={invoiceValidationDocument(caseName)} />
    </div>
  </div>,
);
