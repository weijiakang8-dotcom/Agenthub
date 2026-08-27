import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useExecutionWebSocket } from "@/hooks/useExecutionWebSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
}

describe("useExecutionWebSocket", () => {
  afterEach(() => {
    FakeWebSocket.instances = [];
    localStorage.clear();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reconnects from the last durable sequence", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const { unmount } = renderHook(() => useExecutionWebSocket("exec-1"));
    const first = FakeWebSocket.instances[0];
    expect(first.url).toContain("after_sequence=0");

    act(() => {
      first.onmessage?.({
        data: JSON.stringify({ event: "step", sequence: 7 }),
      } as MessageEvent);
      first.onclose?.();
      vi.advanceTimersByTime(3000);
    });

    expect(FakeWebSocket.instances[1].url).toContain("after_sequence=7");
    unmount();
  });

  it("does not regress the replay cursor on status events", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const { unmount } = renderHook(() => useExecutionWebSocket("exec-2"));
    const first = FakeWebSocket.instances[0];

    act(() => {
      first.onmessage?.({
        data: JSON.stringify({ event: "step", sequence: 9 }),
      } as MessageEvent);
      first.onmessage?.({
        data: JSON.stringify({ event: "status" }),
      } as MessageEvent);
      first.onclose?.();
      vi.advanceTimersByTime(3000);
    });

    expect(FakeWebSocket.instances[1].url).toContain("after_sequence=9");
    unmount();
  });
});
