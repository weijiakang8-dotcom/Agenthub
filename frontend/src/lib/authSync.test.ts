import { afterEach, describe, expect, it, vi } from "vitest";

import { getAccessToken, setAccessToken, startAuthSync } from "@/lib/api";

class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  close = vi.fn();

  constructor(public name: string) {
    FakeBroadcastChannel.instances.push(this);
  }

  postMessage(data: unknown) {
    for (const instance of FakeBroadcastChannel.instances) {
      if (instance !== this && instance.name === this.name) {
        instance.onmessage?.({ data } as MessageEvent);
      }
    }
  }
}

describe("auth sync", () => {
  afterEach(() => {
    FakeBroadcastChannel.instances = [];
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("synchronizes rotated access tokens across tabs", () => {
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    const dispose = startAuthSync();
    const sender = new FakeBroadcastChannel("agenthub.auth");

    sender.postMessage({ event: "access-token", accessToken: "rotated" });

    expect(getAccessToken()).toBe("rotated");
    dispose();
  });

  it("clears tokens and notifies on cross-tab logout", () => {
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    setAccessToken("active");
    const onLogout = vi.fn();
    const dispose = startAuthSync(onLogout);
    const sender = new FakeBroadcastChannel("agenthub.auth");

    sender.postMessage({ event: "logout" });

    expect(getAccessToken()).toBeNull();
    expect(onLogout).toHaveBeenCalledOnce();
    dispose();
  });
});
