import { describe, expect, it } from "vitest";
import { sidePanelConfiguration } from "../src/sidepanel-lifecycle";

describe("tab-specific side panel lifecycle", () => {
  it("creates a distinct panel path for each supported video tab", () => {
    const url = "https://www.bilibili.com/video/BV1xx411c7mD?p=1";
    expect(sidePanelConfiguration(11, url)).toEqual({
      enabled: true,
      path: "sidepanel.html?tabId=11",
    });
    expect(sidePanelConfiguration(12, url)).toEqual({
      enabled: true,
      path: "sidepanel.html?tabId=12",
    });
  });

  it("disables the panel outside ordinary Bilibili video pages", () => {
    expect(sidePanelConfiguration(11, "https://www.bilibili.com/")).toEqual({ enabled: false });
    expect(sidePanelConfiguration(11, "https://example.com/")).toEqual({ enabled: false });
    expect(sidePanelConfiguration(11, undefined)).toEqual({ enabled: false });
  });
});
