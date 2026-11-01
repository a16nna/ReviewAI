import api, { errMsg, readCookie } from "../api";

describe("errMsg", () => {
  it("returns string details from the API", () => {
    expect(errMsg({ response: { data: { detail: "Review not found" } } })).toBe("Review not found");
  });
  it("joins FastAPI validation errors", () => {
    expect(errMsg({ response: { data: { detail: [{ msg: "a" }, { msg: "b" }] } } })).toBe("a; b");
  });
  it("explains network failures", () => {
    expect(errMsg({ message: "Network Error" })).toMatch(/Cannot reach the backend/);
  });
  it("falls back to a generic message", () => {
    expect(errMsg({})).toBe("Request failed");
  });
});

describe("CSRF header", () => {
  let seen;
  beforeEach(() => {
    seen = null;
    api.defaults.adapter = async (config) => {
      seen = config;
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  });

  it("sends the csrf cookie as X-CSRF-Token on state-changing requests", async () => {
    document.cookie = "csrf_token=abc%20def; path=/";
    for (const method of ["post", "delete"]) {
      await api[method]("/x");
      expect(seen.headers.get("X-CSRF-Token")).toBe("abc def");
    }
  });

  it("does not send it on reads or when the cookie is absent", async () => {
    document.cookie = "csrf_token=abc; path=/";
    await api.get("/x");
    expect(seen.headers.get("X-CSRF-Token")).toBeFalsy();
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    await api.post("/x");
    expect(seen.headers.get("X-CSRF-Token")).toBeFalsy();
  });

  it("always sends credentials so the session cookie is included", async () => {
    await api.get("/x");
    expect(seen.withCredentials).toBe(true);
    expect(readCookie("nope")).toBeNull();
  });
});
