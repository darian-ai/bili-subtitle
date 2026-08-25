import { describe, expect, it } from "vitest";
import { activeChapter, activeCue, parseVideoContext } from "../src/video-context";

describe("video context", () => {
  it("recognizes BV, P and playback time", () => {
    expect(parseVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=3", 12.345)).toEqual({
      supported: true, bvid: "BV1xx411c7mD", page: 3, currentTimeMs: 12345
    });
  });

  it("rejects unsupported pages and invalid P", () => {
    expect(parseVideoContext("https://example.com/video/BV1xx411c7mD", 0).supported).toBe(false);
    expect(parseVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=no", 0).page).toBe(1);
  });

  it("follows a chapter without pausing or generating", () => {
    const chapters = [{ id: "a", start_ms: 0, end_ms: 999 }, { id: "b", start_ms: 1000, end_ms: 2000 }];
    expect(activeChapter(chapters, 1500)?.id).toBe("b");
    expect(activeChapter(chapters, 3000)).toBeUndefined();
  });

  it("leaves cue gaps empty and picks the latest overlapping cue", () => {
    const cues = [
      { id: "first", start_ms: 0, end_ms: 1000 },
      { id: "overlap", start_ms: 800, end_ms: 1500 },
      { id: "later", start_ms: 2000, end_ms: 2500 },
    ];
    expect(activeCue(cues, 799)?.id).toBe("first");
    expect(activeCue(cues, 900)?.id).toBe("overlap");
    expect(activeCue(cues, 1500)).toBeUndefined();
    expect(activeCue(cues, 2000)?.id).toBe("later");
  });
});
