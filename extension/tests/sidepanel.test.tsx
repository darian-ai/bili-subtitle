import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  localApi: vi.fn(), storedGuide: false,
  transcriptOnly: false,
  workspace: undefined as undefined | Record<string, unknown>,
}));

vi.mock("../src/local-api", () => ({ localApi: mocks.localApi }));
vi.mock("../src/api", () => ({
  ApiError: class ApiError extends Error { status = 500; body = undefined; },
  OpenAPI: {},
  DefaultService: {
    health: () => ({ operation: "health" }),
    listLibraries: () => ({ operation: "libraries" }),
    inspectVideo: () => ({ operation: "inspect" }),
    prepareTranscript: (args: unknown) => ({ operation: "prepare-transcript", args }),
    getTranscript: () => ({ operation: "transcript" }),
    getJob: ({ jobId }: { jobId: string }) => ({ operation: "job", jobId }),
    createStudyGuide: (args: unknown) => ({ operation: "guide", args }),
    cancelJob: () => ({ operation: "cancel" }),
    retryJob: () => ({ operation: "retry" }),
    getStudyGuide: () => ({ operation: "guide-read" }),
    getStudyGuideWorkspace: () => ({ operation: "guide-workspace" }),
    getVideoWorkspace: (args: unknown) => ({ operation: "workspace", args }),
    createChapterDetail: () => ({ operation: "detail" }),
    createChapterPractice: () => ({ operation: "practice" }),
    createReflection: () => ({ operation: "reflection" }),
    createNote: () => ({ operation: "note" }),
    pair: () => ({ operation: "pair" }),
  },
}));

import { App } from "../entrypoints/sidepanel/App";

const guide = {
  guide_id: "guide-1",
  revision_id: "revision-1",
  learning_objectives: ["理解主要内容"],
  chapters: [{
    chapter_id: "ch001", title: "主要章节", summary: "轻量摘要",
    evidence: { start_cue_id: "c000001", end_cue_id: "c000003" },
    start_ms: 0, end_ms: 3000, questions: [],
  }],
  details: {},
  practices: {
    ch001: { questions: [{
      question_id: "q1", text: "核心是什么？",
      evidence: { start_cue_id: "c000001", end_cue_id: "c000003" },
      start_ms: 0, end_ms: 3000,
    }] },
  },
};

const transcript = {
  revision_id: "revision-1", bvid: "BV1xx411c7mD", page: 1, cid: 1, title: "第一集",
  track_id: "2080600637229272576", language: "zh", display_name: "中文", kind: "ai",
  content_sha256: "hash", created_at: "now",
  cues: [
    { cue_id: "c000001", start_ms: 0, end_ms: 1000, text: "第一句" },
    { cue_id: "c000002", start_ms: 1200, end_ms: 2500, text: "第二句" },
  ],
};

let container: HTMLDivElement;
let root: Root;

function button(label: string): HTMLButtonElement {
  const match = [...container.querySelectorAll("button")].find((item) => item.textContent === label);
  if (!(match instanceof HTMLButtonElement)) throw new Error(`button not found: ${label}`);
  return match;
}

async function flush(action?: () => void): Promise<void> {
  await act(async () => {
    action?.();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

beforeEach(async () => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(globalThis, "chrome", { configurable: true, value: {
    storage: { local: {
      get: vi.fn().mockResolvedValue({ token: "token", endpoint: "http://127.0.0.1:8765", provider: "p", library: "main" }),
      set: vi.fn().mockResolvedValue(undefined),
    } },
    tabs: {
      query: vi.fn().mockResolvedValue([{ id: 1 }]),
      sendMessage: vi.fn().mockResolvedValue({ supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0 }),
    },
    runtime: {
      getURL: vi.fn(() => "chrome-extension://test/"),
      onMessage: { addListener: vi.fn(), removeListener: vi.fn() },
    },
  } });
  mocks.storedGuide = false;
  mocks.transcriptOnly = false;
  mocks.workspace = undefined;
  mocks.localApi.mockImplementation(async (request: { operation: string; jobId?: string; args?: any }) => {
    if (request.operation === "health") return { status: "ok" };
    if (request.operation === "libraries") return { libraries: [{ id: "1", name: "main" }] };
    if (request.operation === "inspect") return { job_id: "inspect-job" };
    if (request.operation === "prepare-transcript") return { job_id: "transcript-job" };
    if (request.operation === "transcript") return transcript;
    if (request.operation === "guide") return { job_id: "guide-job" };
    if (request.operation === "guide-read") return guide;
    if (request.operation === "guide-workspace") {
      mocks.storedGuide = true;
      return mocks.workspace ?? { guide, notes: [], reflections: [] };
    }
    if (request.operation === "workspace") return {
      bvid: request.args?.bvid,
      page: request.args?.page,
      guide_id: mocks.storedGuide && request.args?.bvid === "BV1xx411c7mD" ? "guide-1" : null,
      revision_id: (mocks.storedGuide || mocks.transcriptOnly)
        && request.args?.bvid === "BV1xx411c7mD" ? "revision-1" : null,
    };
    if (request.operation === "job" && request.jobId === "inspect-job") return {
      status: "succeeded", progress: { phase: "completed", percent: 100 },
      result: {
        source_id: "source", bvid: "BV1xx411c7mD", page: 1, cid: 1, title: "视频",
        subtitle_status: "available",
        tracks: [{ track_id: "2080600637229272576", language: "zh", display_name: "中文", kind: "ai" }],
      },
    };
    if (request.operation === "job" && request.jobId === "transcript-job") return {
      status: "succeeded", progress: { phase: "completed", percent: 100 },
      result: { bvid: "BV1xx411c7mD", page: 1, revision_id: "revision-1" },
    };
    if (request.operation === "job") return {
      status: "succeeded", progress: { phase: "completed", percent: 100 },
      result: { guide_id: "guide-1", bvid: "BV1xx411c7mD", page: 1, revision_id: "revision-1" },
    };
    return {};
  });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await flush(() => root.render(<App tabId={1} />));
});

afterEach(async () => {
  await flush(() => root.unmount());
  container.remove();
  mocks.localApi.mockReset();
});

it("shows both the global collection position and the selected P", async () => {
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;
  const context = {
    supported: true, bvid: "BV1yANy6mEWe", page: 6, currentTimeMs: 12_000,
    identity_state: "resolved", identity_evidence: "video_pod_item",
    collection_index: 30, collection_total: 64,
  };
  sendMessage.mockResolvedValue(context);
  await flush(() => listener({ type: "video-navigation", tabId: 1, context }));
  await flush();

  expect(container.textContent).toContain("BV1yANy6mEWe");
  expect(container.textContent).toContain("合集第 30 / 64 项 · P6 · 0:12");
});

it("uses one coherent waiting status while a supported page is transitioning", async () => {
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;
  const context = {
    supported: true, identity_state: "transitioning", currentTimeMs: 0,
  };
  sendMessage.mockResolvedValue(context);
  await flush(() => listener({ type: "video-navigation", tabId: 1, context }));
  await flush();

  expect(container.textContent).toContain("正在确认当前视频分集");
  expect(container.textContent).toContain("播放器正在切换选集");
  expect(container.textContent).not.toContain("请打开受支持的视频页");
  expect(button("检查字幕").disabled).toBe(true);
});

it("keeps outline, practice, and notes on separate pages", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
  await flush(() => button("确认并开始").click());
  expect(container.textContent).toContain("主要章节");
  expect(container.textContent).not.toContain("核心是什么？");

  await flush(() => button("练习").click());
  expect(container.textContent).toContain("核心是什么？");
  expect(container.textContent).not.toContain("当前视频");

  await flush(() => button("笔记").click());
  expect(container.textContent).toContain("时间戳笔记");
  expect(container.textContent).not.toContain("核心是什么？");
});

it("prepares a server-bound transcript and generates only from its revision", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
  const prepare = mocks.localApi.mock.calls
    .map(([value]) => value)
    .find((value: any) => value.operation === "prepare-transcript") as any;
  expect(prepare.args.requestBody).toMatchObject({
    inspect_job_id: "inspect-job",
    track_id: "2080600637229272576",
    track_language: "zh",
    track_display_name: "中文",
    track_kind: "ai",
  });
  expect(mocks.localApi.mock.calls.some(([value]) => value.operation === "guide")).toBe(false);
  await flush(() => button("确认并开始").click());
  const request = mocks.localApi.mock.calls.map(([value]) => value)
    .find((value: any) => value.operation === "guide") as any;
  expect(request.args.requestBody).toMatchObject({
    revision_id: "revision-1", expected_bvid: "BV1xx411c7mD", expected_page: 1,
  });
  expect(request.args.requestBody).not.toHaveProperty("cid");
});

it("does not mistake a transcript-only workspace for an existing guide", async () => {
  mocks.transcriptOnly = true;
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;
  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0 },
  }));
  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0 },
  }));
  await flush();
  expect(container.textContent).toContain("尚未创建学习大纲");
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
  expect(container.textContent).toContain("确认发送字幕");
  expect(mocks.localApi.mock.calls.some(([value]) => value.operation === "guide")).toBe(false);
});

it("isolates navigation events by tab and restores a video session", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
  await flush(() => button("确认并开始").click());
  expect(container.textContent).toContain("主要章节");
  const addListener = chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>;
  const listener = addListener.mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;

  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 2,
    context: { supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0 },
  }));
  expect(container.textContent).toContain("主要章节");

  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0 },
  }));
  expect(container.textContent).not.toContain("主要章节");

  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0 },
  }));
  expect(container.textContent).toContain("主要章节");
});

it("restores all saved pages without creating another guide", async () => {
  mocks.storedGuide = true;
  mocks.workspace = {
    guide,
    notes: [{
      note_id: "note-1", revision_id: "revision-1", timestamp_ms: 1200,
      note_type: "note", body: "保存的笔记", created_at: "now", updated_at: "now",
    }],
    reflections: [{
      reflection_id: "reflection-1", guide_id: "guide-1", question_id: "q1",
      response: "保存的回答", status: "succeeded",
      feedback: { covered: ["已掌握"], missing: [], misconceptions: [] },
    }],
  };
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;
  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1yy411c7mD", page: 1, currentTimeMs: 0 },
  }));
  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0 },
  }));
  await flush();
  expect(container.textContent).toContain("主要章节");

  await flush(() => button("练习").click());
  expect(container.textContent).toContain("保存的回答");
  expect(container.textContent).toContain("已掌握");
  await flush(() => button("笔记").click());
  expect(container.textContent).toContain("保存的笔记");
  expect(mocks.localApi.mock.calls.some(([value]) => value.operation === "guide")).toBe(false);
});

it("shows the complete timeline, highlights the current cue, and seeks without pausing", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("字幕").click());
  expect(container.textContent).toContain("第一句");
  expect(container.textContent).toContain("第二句");
  const current = container.querySelector('[aria-current="true"]');
  expect(current?.textContent).toContain("第一句");
  const second = [...container.querySelectorAll("button.cue")][1] as HTMLButtonElement;
  await flush(() => second.click());
  expect(chrome.tabs.sendMessage).toHaveBeenCalledWith(1, { type: "seek", timestampMs: 1200 });
  expect(chrome.tabs.sendMessage).not.toHaveBeenCalledWith(1, expect.objectContaining({ type: "pause" }));

  const list = container.querySelector(".transcript-list")!;
  await flush(() => list.dispatchEvent(new Event("scroll", { bubbles: true })));
  expect(container.textContent).toContain("回到当前字幕");
  await flush(() => button("回到当前字幕").click());
  expect(container.textContent).not.toContain("回到当前字幕");
});

it("writes a late P1 inspection back to P1 after switching to P2", async () => {
  const original = mocks.localApi.getMockImplementation()!;
  let finishInspection: ((value: unknown) => void) | undefined;
  mocks.localApi.mockImplementation(async (request: { operation: string; jobId?: string }) => {
    if (request.operation === "job" && request.jobId === "inspect-job") {
      return new Promise((resolve) => { finishInspection = resolve; });
    }
    return original(request);
  });
  await flush(() => button("检查字幕").click());
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;
  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1xx411c7mD", page: 2, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1xx411c7mD", page: 2, currentTimeMs: 0 },
  }));
  await flush(() => finishInspection?.({
    status: "succeeded", progress: { phase: "completed", percent: 100 },
    result: {
      bvid: "BV1xx411c7mD", page: 1, subtitle_status: "available",
      tracks: [{ track_id: "99", language: "zh", display_name: "P1专属", kind: "ai" }],
    },
  }));
  expect(container.textContent).toContain("P2");
  expect(container.textContent).not.toContain("P1专属");

  sendMessage.mockResolvedValue({
    supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0,
  });
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1xx411c7mD", page: 1, currentTimeMs: 0 },
  }));
  expect(container.textContent).toContain("P1专属");
});

it("ignores an older video-context poll that returns after a newer navigation", async () => {
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const sendMessage = chrome.tabs.sendMessage as ReturnType<typeof vi.fn>;
  let resolveOld: ((value: unknown) => void) | undefined;
  let resolveNew: ((value: unknown) => void) | undefined;
  sendMessage
    .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
    .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve; }));

  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1xx411c7mD", page: 2, currentTimeMs: 0 },
  }));
  await flush(() => listener({
    type: "video-navigation", tabId: 1,
    context: { supported: true, bvid: "BV1yy411c7mD", page: 3, currentTimeMs: 0 },
  }));
  await flush(() => resolveNew?.({
    supported: true, bvid: "BV1yy411c7mD", page: 3, currentTimeMs: 0,
  }));
  await flush(() => resolveOld?.({
    supported: true, bvid: "BV1xx411c7mD", page: 2, currentTimeMs: 0,
  }));

  expect(container.textContent).toContain("BV1yy411c7mD");
  expect(container.textContent).toContain("P3");
  expect(container.textContent).not.toContain("P2");
});

it("rejects a guide workspace whose transcript belongs to another BV/P", async () => {
  const original = mocks.localApi.getMockImplementation()!;
  mocks.localApi.mockImplementation(async (request: { operation: string; args?: any }) => {
    if (request.operation === "workspace") return {
      bvid: request.args?.bvid, page: request.args?.page,
      guide_id: "guide-1", revision_id: "revision-1",
    };
    if (request.operation === "guide-workspace") return { guide, notes: [], reflections: [] };
    if (request.operation === "transcript") return transcript;
    return original(request);
  });
  const listener = (chrome.runtime.onMessage.addListener as ReturnType<typeof vi.fn>)
    .mock.calls[0]![0] as (message: unknown) => void;
  const context = { supported: true, bvid: "BV1yy411c7mD", page: 2, currentTimeMs: 0 };
  (chrome.tabs.sendMessage as ReturnType<typeof vi.fn>).mockResolvedValue(context);
  await flush(() => listener({ type: "video-navigation", tabId: 1, context }));
  await flush();

  expect(container.textContent).toContain("读取已有学习记录失败");
  expect(container.textContent).not.toContain("主要章节");
});

it("synchronously deduplicates repeated inspect clicks", async () => {
  const original = mocks.localApi.getMockImplementation()!;
  let finishInspection: ((value: unknown) => void) | undefined;
  mocks.localApi.mockImplementation(async (request: { operation: string; jobId?: string }) => {
    if (request.operation === "job" && request.jobId === "inspect-job") {
      return new Promise((resolve) => { finishInspection = resolve; });
    }
    return original(request);
  });
  await flush(() => {
    button("检查字幕").click();
    button("检查字幕").click();
  });
  const inspectCalls = mocks.localApi.mock.calls
    .filter(([request]) => request.operation === "inspect");
  expect(inspectCalls).toHaveLength(1);
  await flush(() => finishInspection?.({
    status: "succeeded", progress: { phase: "completed", percent: 100 },
    result: { bvid: "BV1xx411c7mD", page: 1, subtitle_status: "no_subtitles", tracks: [] },
  }));
});
