import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Findings from "../components/Findings.jsx";
import { finding } from "./helpers.jsx";

const list = [
  finding({ id: "a", severity: "Low", title: "Style nit", source: "static_analysis", analyzer: "ruff" }),
  finding({ id: "b", severity: "Critical", title: "SQL injection", source: "ai", analyzer: null, certainty: "possible" }),
];

describe("Findings", () => {
  it("shows verified evidence for AI findings", () => {
    render(<Findings findings={[finding({ id: "g1", source: "ai", analyzer: null, title: "Unchecked division", severity: "Medium", certainty: "possible", evidence: "return a / b", line_start: 4, line_end: 4 })]} />);
    expect(screen.getByText("Evidence:")).toBeInTheDocument();
    expect(screen.getByText("return a / b")).toBeInTheDocument();
    expect(screen.getByText("AI suggestion")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<Findings findings={[]} />);
    expect(screen.getByText(/No findings were reported/)).toBeInTheDocument();
  });

  it("labels source, certainty and severity, most severe first", () => {
    render(<Findings findings={list} />);
    const titles = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual(["SQL injection", "Style nit"]);
    expect(screen.getByText("AI suggestion")).toBeInTheDocument();
    expect(screen.getByText("Static analysis: ruff")).toBeInTheDocument();
    expect(screen.getByText("Possible")).toBeInTheDocument();
  });

  it("filters by severity, source and text", async () => {
    const user = userEvent.setup();
    render(<Findings findings={list} />);
    await user.selectOptions(screen.getByLabelText("Filter by severity"), "Low");
    expect(screen.getByText("1 of 2 findings")).toBeInTheDocument();
    expect(screen.queryByText("SQL injection")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Filter by severity"), "");
    await user.selectOptions(screen.getByLabelText("Filter by source"), "ai");
    expect(screen.getByText("SQL injection")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Search findings"), "nothing-matches");
    expect(screen.getByText(/No findings match the filters/)).toBeInTheDocument();
  });

  it("renders untrusted content as inert text", () => {
    const evil = '<img src=x onerror="window.pwned=1">';
    const { container } = render(<Findings findings={[finding({ title: evil, description: evil })]} />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByText(evil).length).toBeGreaterThan(0);
  });

  it("shows original vs suggested code", () => {
    render(<Findings code={"a = 1\nx = eval(y)\n"} findings={[finding({ corrected_code: "x = ast.literal_eval(y)" })]} />);
    expect(screen.getByText("x = eval(y)")).toBeInTheDocument();
    expect(screen.getByText("x = ast.literal_eval(y)")).toBeInTheDocument();
  });

  it("only offers selection for findings that map to a file line", async () => {
    const onToggle = vi.fn();
    render(<Findings selectable selected={new Set()} onToggle={onToggle}
      findings={[finding({ id: "m", file_path: "a.py" }), finding({ id: "n", title: "No line", line_start: null })]} />);
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(1);
    await userEvent.click(boxes[0]);
    expect(onToggle).toHaveBeenCalledWith("m");
  });
});
