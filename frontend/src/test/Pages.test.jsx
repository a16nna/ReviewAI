import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import api from "../api";
import App from "../App.jsx";
import Dashboard from "../pages/Dashboard.jsx";
import GitHubPage from "../pages/GitHubPage.jsx";
import History from "../pages/History.jsx";
import ReviewDetail from "../pages/ReviewDetail.jsx";
import Settings from "../pages/Settings.jsx";
import { finding, renderAt, review } from "./helpers.jsx";

vi.mock("@monaco-editor/react", () => ({ default: () => <div /> }));
vi.mock("recharts", async () => {
  const Stub = ({ children }) => <div>{children}</div>;
  return { ResponsiveContainer: Stub, BarChart: Stub, LineChart: Stub, Bar: Stub, Line: Stub, XAxis: Stub, YAxis: Stub, CartesianGrid: Stub, Tooltip: Stub };
});
vi.mock("../api", async (orig) => {
  const real = await orig();
  return { ...real, default: { post: vi.fn(), get: vi.fn(), delete: vi.fn() } };
});

const route = (url, data) => api.get.mockImplementation((u, cfg) => {
  const h = data[u];
  return h === undefined ? Promise.reject({ response: { data: { detail: "Not found" } } })
    : Promise.resolve({ data: typeof h === "function" ? h(cfg) : h });
});
const STATS = { total_reviews: 2, by_severity: { High: 1 }, by_category: { Security: 1 }, by_day: [{ date: "2026-10-01", count: 2 }],
  recent: [{ id: "r1", created_at: "2026-10-01T10:00:00", language: "python", findings: 1, is_mock: false }] };

beforeEach(() => { vi.clearAllMocks(); vi.spyOn(window, "confirm").mockReturnValue(true); });

describe("navigation", () => {
  it("opens on the landing page and navigates via the nav bar", async () => {
    route("", { "/stats": { ...STATS, total_reviews: 0, recent: [] } });
    const user = userEvent.setup();
    renderAt(<App />);
    expect(screen.getByRole("heading", { name: /AI-powered code review/ })).toBeInTheDocument();
    await user.click(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Dashboard" }));
    expect(await screen.findByText("No reviews yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Run your first review" }));
    expect(screen.getByLabelText("Language")).toBeInTheDocument();
  });

  it("landing call-to-action opens the workspace; unknown routes show a message", async () => {
    const user = userEvent.setup();
    const { unmount } = renderAt(<App />);
    await user.click(screen.getByRole("link", { name: "Open review workspace" }));
    expect(screen.getByRole("button", { name: "Analyze" })).toBeInTheDocument();
    unmount();
    renderAt(<App />, "/nope");
    expect(screen.getByText("Page not found.")).toBeInTheDocument();
  });
});

describe("Dashboard", () => {
  it("renders stats from the API", async () => {
    route("", { "/stats": STATS });
    renderAt(<Dashboard />);
    expect(await screen.findByText("Total reviews")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all history" })).toHaveAttribute("href", "/history");
  });
  it("shows an error state", async () => {
    api.get.mockRejectedValue({ message: "Network Error" });
    renderAt(<Dashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the backend/);
  });
});

describe("History", () => {
  it("lists reviews, sends filters to the API and deletes after confirmation", async () => {
    route("", { "/reviews": [review({ id: "r1" }), review({ id: "r2", is_mock: true, provider: "mock" })] });
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderAt(<History />);
    expect(await screen.findAllByRole("link", { name: /2026|10\/1|1\/10/ })).toHaveLength(2);
    expect(screen.getByText("mock (mock)")).toBeInTheDocument();
    expect(screen.getByText("gemini")).toBeInTheDocument();  // real provider is shown without a mock label
    await user.selectOptions(screen.getByLabelText("Severity filter"), "High");
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith("/reviews", { params: expect.objectContaining({ severity: "High" }) }));
    await user.click(screen.getByRole("button", { name: "Delete review r1" }));
    expect(api.delete).toHaveBeenCalledWith("/reviews/r1");
    expect(await screen.findByRole("status")).toHaveTextContent("Review deleted.");
  });
  it("shows an empty state when nothing matches", async () => {
    route("", { "/reviews": [] });
    renderAt(<History />);
    expect(await screen.findByText(/No reviews match/)).toBeInTheDocument();
  });
  it("does not delete when the confirmation is cancelled", async () => {
    window.confirm.mockReturnValue(false);
    route("", { "/reviews": [review()] });
    renderAt(<History />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete review r1" }));
    expect(api.delete).not.toHaveBeenCalled();
  });
});

describe("ReviewDetail", () => {
  const detail = () => renderAt(<Routes><Route path="/reviews/:id" element={<ReviewDetail />} /><Route path="/history" element={<p>history page</p>} /></Routes>, "/reviews/r1");
  it("shows the review, export links and deletes it", async () => {
    route("", { "/reviews/r1": review() });
    api.delete.mockResolvedValue({});
    detail();
    expect(await screen.findByText("Use of eval")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export Markdown" })).toHaveAttribute("href", "/api/reviews/r1/report?format=md");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText("history page")).toBeInTheDocument();
  });
  it("shows a not-found state", async () => {
    route("", {});
    detail();
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found");
  });
});

describe("Settings", () => {
  const base = { "/capabilities": { ai_provider: "mock", retention_days: 0, languages: { python: { ruff: "available" }, java: { checkstyle: "unavailable: java is not installed" } } },
    "/health": { mode: "demo (mock AI)" } };
  it("shows demo mode, analyzer availability and a disabled GitHub connect when unconfigured", async () => {
    route("", { ...base, "/github/status": { configured: false, connected: false, scope: "public_repo" } });
    renderAt(<Settings />);
    expect(await screen.findByText(/Mode: demo \(mock AI\)/)).toBeInTheDocument();
    expect(screen.getByText(/checkstyle unavailable/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Connect GitHub" })).toBeDisabled();
  });
  it("shows Gemini as the active provider with its model, without any key", async () => {
    route("", { "/capabilities": { ai_provider: "gemini", ai: { provider: "gemini", state: "gemini", model: "gemini-test", message: "ok" }, retention_days: 0, languages: {} },
      "/health": { mode: "live AI" }, "/github/status": { configured: false, connected: false, scope: "public_repo" } });
    renderAt(<Settings />);
    expect(await screen.findByText("Gemini")).toBeInTheDocument();
    expect(screen.getByText("gemini-test")).toBeInTheDocument();
    expect(screen.queryByText(/GEMINI_API_KEY=/)).not.toBeInTheDocument();
  });
  it("tells the user to set GEMINI_API_KEY in mock mode", async () => {
    route("", { "/capabilities": { ai_provider: "mock", ai: { provider: "mock", state: "mock", model: null, message: "GEMINI_API_KEY is not set. Set it in backend/.env and restart to enable real AI review." }, retention_days: 0, languages: {} },
      "/health": { mode: "demo (mock AI)" }, "/github/status": { configured: false, connected: false, scope: "public_repo" } });
    renderAt(<Settings />);
    expect(await screen.findByText(/Mock \(demo, not real AI\)/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("GEMINI_API_KEY is not set");
  });
  it("shows an alert when the provider is unavailable", async () => {
    route("", { "/capabilities": { ai_provider: "unavailable", ai: { provider: "unavailable", state: "unavailable", model: null, message: "google-genai is not installed" }, retention_days: 0, languages: {} },
      "/health": { mode: "AI unavailable" }, "/github/status": { configured: false, connected: false, scope: "public_repo" } });
    renderAt(<Settings />);
    expect(await screen.findByRole("alert")).toHaveTextContent("google-genai is not installed");
  });
  it("shows the connected account and disconnects", async () => {
    route("", { ...base, "/github/status": { configured: true, connected: true, login: "octocat", scope: "public_repo" } });
    api.post.mockResolvedValue({});
    renderAt(<Settings />);
    expect(await screen.findByText("octocat")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(api.post).toHaveBeenCalledWith("/github/logout");
  });
});

describe("GitHubPage", () => {
  it("tells unconnected users where to connect", async () => {
    route("", { "/github/status": { connected: false } });
    renderAt(<GitHubPage />);
    expect(await screen.findByText("GitHub is not connected.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("reviews a PR and only publishes selected comments after explicit confirmation", async () => {
    route("", {
      "/github/status": { connected: true, login: "me" },
      "/github/repos": [{ full_name: "o/r", private: false }],
      "/github/repos/o/r/branches": [{ name: "main" }],
      "/github/repos/o/r/pulls": [{ number: 5, title: "Add feature", author: "dev" }],
    });
    api.post.mockImplementation((url) => Promise.resolve({ data: url.endsWith("/review")
      ? { ...review({ repo: "o/r", pr_number: 5, findings: [finding({ id: "x1", file_path: "a.py", line_start: 3 })] }), review_id: "r9", head_sha: "abc1234", files_reviewed: 1, files_skipped: [{ filename: "README.md", reason: "not a supported language" }] }
      : { published: 1 } }));
    const user = userEvent.setup();
    renderAt(<GitHubPage />);
    await user.selectOptions(await screen.findByLabelText("Repository"), "o/r");
    await user.click(await screen.findByRole("button", { name: "Review" }));
    expect(await screen.findByText("Use of eval")).toBeInTheDocument();
    expect(screen.getByText(/README.md: not a supported language/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish comments" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /Select finding/ }));
    const publish = screen.getByRole("button", { name: "Publish comments" });
    expect(publish).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /I confirm/ }));
    await user.click(publish);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/github/repos/o/r/pulls/5/publish",
      expect.objectContaining({ confirm: true, head_sha: "abc1234", comments: [expect.objectContaining({ path: "a.py", line: 3 })] })));
    expect(await screen.findByText(/Published 1 comment/)).toBeInTheDocument();
  });

  it("shows GitHub permission errors", async () => {
    route("", { "/github/status": { connected: true }, "/github/repos": [{ full_name: "o/r" }] });
    api.get.mockImplementation((u) => u === "/github/status" ? Promise.resolve({ data: { connected: true } })
      : u === "/github/repos" ? Promise.resolve({ data: [{ full_name: "o/r" }] })
      : Promise.reject({ response: { data: { detail: "GitHub denied the request (missing permission, SSO, or rate limit)" } } }));
    renderAt(<GitHubPage />);
    await userEvent.selectOptions(await screen.findByLabelText("Repository"), "o/r");
    expect(await screen.findByRole("alert")).toHaveTextContent(/GitHub denied/);
  });
});
