import { describe, expect, it } from "vitest";
import { activeChapter, activeCue, parseVideoContext, resolveVideoContext } from "../src/video-context";

describe("video context", () => {
  it("recognizes BV, P and playback time", () => {
    expect(parseVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=3", 12.345)).toEqual({
      supported: true, bvid: "BV1xx411c7mD", page: 3, identity_state: "resolved",
      identity_evidence: "url_page", currentTimeMs: 12345
    });
  });

  it("rejects unsupported pages and invalid P", () => {
    for (const url of [
      "https://example.com/video/BV1xx411c7mD",
      "https://www.bilibili.com/bangumi/play/ep123",
      "https://www.bilibili.com/cheese/play/ep123",
      "https://live.bilibili.com/123",
      "https://www.bilibili.com/festival/example?bvid=BV1xx411c7mD",
      "https://www.bilibili.com/medialist/play/123/BV1xx411c7mD",
      "https://space.bilibili.com/123/lists/456",
    ]) {
      expect(parseVideoContext(url, 0).supported, url).toBe(false);
    }
    expect(parseVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=no", 0).identity_state)
      .toBe("ambiguous");
  });

  it("binds a multi-BV video pod item and blocks transitional conflicts", () => {
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1yy411c7mD", 1, {
      metadata: { bvid: "BV1yy411c7mD", page: 1 },
      pod: { kind: "collection", selectedBvid: "BV1yy411c7mD", selectedPage: 1,
        multiplePages: false, collectionIndex: 3, collectionTotal: 10 },
    })).toMatchObject({
      bvid: "BV1yy411c7mD", page: 1, identity_state: "resolved",
      identity_evidence: "video_pod_item", collection_index: 3, collection_total: 10,
    });
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1xx411c7mD", 1, {
      pod: { kind: "collection", selectedBvid: "BV1yy411c7mD", selectedPage: 1 },
    }).identity_state).toBe("transitioning");
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1xx411c7mD", 1, {})
      .identity_state).toBe("resolved");
  });

  it("derives a same-BV multi-P page from the stable pod index", () => {
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=3", 1, {
      metadata: { bvid: "BV1xx411c7mD", page: 3 },
      pod: { kind: "pages", selectedPage: 3, playerPage: 3,
        selectedCid: "333", playerCid: "333" },
    })).toMatchObject({
      bvid: "BV1xx411c7mD", page: 3, identity_state: "resolved",
      identity_evidence: "video_pod_page",
    });
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=1", 1, {
      metadata: { bvid: "BV1xx411c7mD", page: 1 },
      pod: { kind: "pages", selectedPage: 3, playerPage: 3,
        selectedCid: "333", playerCid: "333" },
    }).identity_state).toBe("transitioning");
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1xx411c7mD?p=3", 1, {
      metadata: { bvid: "BV1xx411c7mD", page: 3 },
      pod: { kind: "pages", selectedPage: 3, selectedCid: "333" },
    })).toMatchObject({
      bvid: "BV1xx411c7mD", page: 3, identity_state: "resolved",
      identity_evidence: "video_pod_page",
    });
  });

  it("resolves a multi-page collection without requiring the player menu", () => {
    expect(resolveVideoContext("https://www.bilibili.com/video/BV1yy411c7mD?p=2", 1, {
      metadata: { bvid: "BV1yy411c7mD", page: 2 },
      pod: { kind: "collection", selectedBvid: "BV1yy411c7mD", selectedPage: 2,
        multiplePages: true, collectionIndex: 4, collectionTotal: 12 },
    })).toMatchObject({
      bvid: "BV1yy411c7mD", page: 2, identity_state: "resolved",
      identity_evidence: "video_pod_item", collection_index: 4,
    });
  });

  it("compares a single-page collection player index with the collection position", () => {
    const url = "https://www.bilibili.com/video/BV1hduL6pEcu/";
    expect(resolveVideoContext(url, 1, {
      metadata: { bvid: "BV1hduL6pEcu", page: 1 },
      pod: { kind: "collection", selectedBvid: "BV1hduL6pEcu", selectedPage: 1,
        multiplePages: false, playerPage: 248, collectionIndex: 248, collectionTotal: 277 },
    })).toMatchObject({
      bvid: "BV1hduL6pEcu", page: 1, identity_state: "resolved",
      identity_evidence: "video_pod_item", collection_index: 248, collection_total: 277,
    });
    expect(resolveVideoContext(url, 1, {
      metadata: { bvid: "BV1hduL6pEcu", page: 1 },
      pod: { kind: "collection", selectedBvid: "BV1hduL6pEcu", selectedPage: 1,
        multiplePages: false, playerPage: 247, collectionIndex: 248 },
    }).identity_state).toBe("transitioning");
  });

  it("blocks metadata, player page and CID conflicts", () => {
    const url = "https://www.bilibili.com/video/BV1xx411c7mD?p=2";
    expect(resolveVideoContext(url, 0, {
      metadata: { bvid: "BV1xx411c7mD", page: 1 },
    }).identity_state).toBe("transitioning");
    expect(resolveVideoContext(url, 0, {
      metadata: { bvid: "BV1xx411c7mD", page: 2 },
      pod: { kind: "pages", selectedPage: 2, playerPage: 1,
        selectedCid: "22", playerCid: "22" },
    }).identity_state).toBe("transitioning");
    expect(resolveVideoContext(url, 0, {
      metadata: { bvid: "BV1xx411c7mD", page: 2 },
      pod: { kind: "pages", selectedPage: 2, playerPage: 2,
        selectedCid: "22", playerCid: "11" },
    }).identity_state).toBe("transitioning");
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
