import "@testing-library/react";
import { vi } from "vitest";

Element.prototype.scrollIntoView = vi.fn();

const navigationMocks = vi.hoisted(() => ({
  push: vi.fn(),
  search: "",
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: navigationMocks.push }),
  useSearchParams: () => new URLSearchParams(navigationMocks.search),
}));

export { navigationMocks };
