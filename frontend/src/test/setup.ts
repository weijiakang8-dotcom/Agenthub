import "@testing-library/jest-dom/vitest";

const memory = new Map<string, string>();
const localStorageMock = {
  get length() {
    return memory.size;
  },
  clear() {
    memory.clear();
  },
  getItem(key: string) {
    return memory.has(key) ? memory.get(key)! : null;
  },
  key(index: number) {
    return Array.from(memory.keys())[index] ?? null;
  },
  removeItem(key: string) {
    memory.delete(key);
  },
  setItem(key: string, value: string) {
    memory.set(key, String(value));
  },
};

try {
  globalThis.localStorage.setItem("__vitest_probe__", "1");
  globalThis.localStorage.removeItem("__vitest_probe__");
} catch {
  Object.defineProperty(globalThis, "localStorage", {
    value: localStorageMock,
    configurable: true,
    writable: true,
  });
}
