import { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installErrorCapture, reportRequestFailure } from "@/lib/clientErrors";

function failure(status: number, detail: unknown, config: Partial<InternalAxiosRequestConfig> = {}) {
  const request = { url: "/api/v1/store/deliveries?x=1", method: "post", ...config } as InternalAxiosRequestConfig;
  return new AxiosError("Request failed", "ERR_BAD_REQUEST", request, {}, {
    status,
    statusText: "",
    headers: {},
    config: request,
    data: { detail },
  });
}

describe("client error capture", () => {
  let stop: (() => void) | null = null;
  afterEach(() => {
    stop?.();
    stop = null;
  });

  it("reports a failed request with its path and reason, once", () => {
    const post = vi.fn().mockResolvedValue({});
    stop = installErrorCapture(post);
    reportRequestFailure(failure(413, "Photo too large"));
    reportRequestFailure(failure(413, "Photo too large"));
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatchObject({
      kind: "request",
      status_code: 413,
      message: "POST /api/v1/store/deliveries failed (413): Photo too large",
    });
  });

  it("ignores expired sign-ins and the report call itself", () => {
    const post = vi.fn().mockResolvedValue({});
    stop = installErrorCapture(post);
    reportRequestFailure(failure(401, "Not authenticated"));
    reportRequestFailure(failure(500, "boom", { skipErrorReport: true }));
    expect(post).not.toHaveBeenCalled();
  });

  it("reports script errors and unhandled rejections but not request failures twice", () => {
    const post = vi.fn().mockResolvedValue({});
    stop = installErrorCapture(post);
    window.dispatchEvent(new ErrorEvent("error", { message: "x is undefined" }));
    const rejection = new Event("unhandledrejection") as PromiseRejectionEvent;
    Object.assign(rejection, { reason: failure(500, "boom") });
    window.dispatchEvent(rejection);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatchObject({ kind: "script", message: "x is undefined" });
  });

  it("stops reporting once removed", () => {
    const post = vi.fn().mockResolvedValue({});
    installErrorCapture(post)();
    reportRequestFailure(failure(500, "boom"));
    expect(post).not.toHaveBeenCalled();
  });
});
