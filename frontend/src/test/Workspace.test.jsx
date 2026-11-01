import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "../api";
import Workspace from "../pages/Workspace.jsx";
import { finding, renderAt, review } from "./helpers.jsx";

vi.mock("@monaco-editor/react", () => ({
  default: ({ value, onChange }) => <textarea aria-label="Code editor" value={value} onChange={(e) => onChange(e.target.value)} />,
}));
vi.mock("../api", async (orig) => {
  const real = await orig();
  return { ...real, default: { post: vi.fn(), get: vi.fn(), delete: vi.fn() } };
});

const clear = async (user) => user.clear(screen.getByLabelText("Code editor"));

describe("Workspace", () => {
  beforeEach(() => vi.clearAllMocks());

  it("rejects empty code without calling the API", async () => {
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await clear(user);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter some code first");
    expect(api.post).not.toHaveBeenCalled();
  });

  it("submits code and renders results with analyzer status and export links", async () => {
    api.post.mockResolvedValue({ data: review({ id: "abc" }) });
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("Use of eval")).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/reviews", expect.objectContaining({ language: "python" }));
    expect(screen.getByText(/ruff:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export Markdown" })).toHaveAttribute("href", "/api/reviews/abc/report?format=md");
    expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute("href", "/api/reviews/abc/report?format=json");
  });

  it("displays Gemini findings next to static-analysis findings", async () => {
    api.post.mockResolvedValue({ data: review({ provider: "gemini", findings: [finding(), finding({ id: "g1", source: "ai", analyzer: null, title: "Unchecked division", severity: "Medium", certainty: "possible", evidence: "return a / b", line_start: 4, line_end: 4 })] }) });
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("Unchecked division")).toBeInTheDocument();
    expect(screen.getByText("Use of eval")).toBeInTheDocument();
    expect(screen.getByText("Static analysis: bandit")).toBeInTheDocument();
    expect(screen.queryByText(/MOCK MODE/)).not.toBeInTheDocument();
  });

  it("clearly labels mock results", async () => {
    api.post.mockResolvedValue({ data: review({ is_mock: true, provider: "mock" }) });
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(/MOCK MODE/)).toBeInTheDocument();
  });

  it("shows provider failures but keeps static results", async () => {
    api.post.mockResolvedValue({ data: review({ ai_error: "AI provider timed out" }) });
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(/AI provider timed out/)).toBeInTheDocument();
    expect(screen.getByText("Use of eval")).toBeInTheDocument();
  });

  it("shows server validation errors", async () => {
    api.post.mockRejectedValue({ response: { data: { detail: [{ msg: "String should have at most 100000 characters" }] } } });
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at most 100000/);
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });

  it("disables the button while analyzing", async () => {
    let resolve;
    api.post.mockReturnValue(new Promise((r) => { resolve = r; }));
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(screen.getByRole("button", { name: "Analyzing…" })).toBeDisabled();
    resolve({ data: review() });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled());
  });

  it("validates uploaded files", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderAt(<Workspace />);
    await user.upload(screen.getByLabelText("Upload file"), new File(["x"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unsupported file type");
  });

  it("loads a supported file and switches language", async () => {
    const user = userEvent.setup();
    renderAt(<Workspace />);
    await user.upload(screen.getByLabelText("Upload file"), new File(["class A {}"], "A.java"));
    await waitFor(() => expect(screen.getByLabelText("Code editor")).toHaveValue("class A {}"));
    expect(screen.getByLabelText("Language")).toHaveValue("java");
    expect(screen.getByText(/Checkstyle/)).toBeInTheDocument();
  });
});
