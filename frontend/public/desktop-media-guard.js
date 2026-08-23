/* global window, navigator, DOMException */
// Desktop-only privacy guard. AgentHub does not use camera or microphone.
(() => {
  const isTauri =
    window.location.protocol === "tauri:" ||
    window.location.hostname === "tauri.localhost" ||
    Boolean(window.__TAURI_INTERNALS__);
  if (!isTauri) return;

  const denied = () =>
    Promise.reject(
      new DOMException(
        "Synplex AgentHub does not request camera or microphone access",
        "NotAllowedError",
      ),
    );

  try {
    if (navigator.mediaDevices) {
      Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
        value: denied,
        configurable: false,
        writable: false,
      });
      Object.defineProperty(navigator.mediaDevices, "enumerateDevices", {
        value: () => Promise.resolve([]),
        configurable: false,
        writable: false,
      });
    }
  } catch {
    // WebKit may expose a non-configurable MediaDevices object; no application code calls it.
  }

  try {
    Object.defineProperty(navigator, "getUserMedia", {
      value: denied,
      configurable: false,
      writable: false,
    });
    Object.defineProperty(navigator, "webkitGetUserMedia", {
      value: denied,
      configurable: false,
      writable: false,
    });
  } catch {
    // Legacy APIs are optional.
  }
})();
