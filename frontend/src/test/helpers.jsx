import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

export const renderAt = (ui, path = "/") => render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>);

export const finding = (o = {}) => ({
  id: "f1", category: "Security", severity: "High", title: "Use of eval", description: "eval runs arbitrary code",
  impact: "", remediation: "Use ast.literal_eval", corrected_code: null, confidence: "high", certainty: "confirmed",
  source: "static_analysis", analyzer: "bandit", file_path: null, line_start: 2, line_end: 2, ...o,
});

export const review = (o = {}) => ({
  id: "r1", created_at: "2026-10-01T10:00:00", language: "python", provider: "gemini", is_mock: false,
  analyzers: { ruff: "ran", bandit: "ran" }, ai_error: null, source_kind: "manual", repo: null, pr_number: null,
  findings: [finding()], ...o,
});
