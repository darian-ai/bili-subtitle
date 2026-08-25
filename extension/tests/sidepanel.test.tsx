import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ localApi: vi.fn() }));

vi.mock("../src/local-api", () => ({ localApi: mocks.localApi }));
vi.mock("../src/api", () => ({
  ApiError: class ApiError extends Error { status = 500; body = undefined; },
  OpenAPI: {},
  DefaultService: {
    health: () => ({ operation: "health" }),
    listLibraries: () => ({ operation: "libraries" }),
    inspectVideo: () => ({ operation: "inspect" }),
    getJob: ({ jobId }: { jobId: string }) => ({ operation: "job", jobId }),
    createStudyGuide: (args: unknown) => ({ operation: "guide", args }),
    getStudyGuide: () => ({ operation: "guide-read" }),
    getVideoWorkspace: () => ({ operation: "workspace" }),
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
  mocks.localApi.mockImplementation(async (request: { operation: string; jobId?: string }) => {
    if (request.operation === "health") return { status: "ok" };
    if (request.operation === "libraries") return { libraries: [{ id: "1", name: "main" }] };
    if (request.operation === "inspect") return { job_id: "inspect-job" };
    if (request.operation === "guide") return { job_id: "guide-job" };
    if (request.operation === "guide-read") return guide;
    if (request.operation === "workspace") return { guide_id: null };
    if (request.operation === "job" && request.jobId === "inspect-job") return {
      status: "succeeded", progress: { phase: "completed", percent: 100 },
      result: {
        source_id: "source", bvid: "BV1xx411c7mD", page: 1, cid: 1, title: "视频",
        subtitle_status: "available",
        tracks: [{ track_id: "2080600637229272576", language: "zh", display_name: "中文", kind: "ai" }],
      },
    };
    if (request.operation === "job") return {
      status: "succeeded", progress: { phase: "completed", percent: 100 },
      result: { guide_id: "guide-1" },
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

it("keeps outline, practice, and notes on separate pages", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
  expect(container.textContent).toContain("主要章节");
  expect(container.textContent).not.toContain("核心是什么？");

  await flush(() => button("练习").click());
  expect(container.textContent).toContain("核心是什么？");
  expect(container.textContent).not.toContain("当前视频");

  await flush(() => button("笔记").click());
  expect(container.textContent).toContain("时间戳笔记");
  expect(container.textContent).not.toContain("核心是什么？");
});

it("sends stable track descriptors when generating a guide", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
  const request = mocks.localApi.mock.calls
    .map(([value]) => value)
    .find((value: any) => value.operation === "guide") as any;
  expect(request.args.requestBody).toMatchObject({
    track_id: "2080600637229272576",
    track_language: "zh",
    track_display_name: "中文",
    track_kind: "ai",
  });
});

it("isolates navigation events by tab and restores a video session", async () => {
  await flush(() => button("检查字幕").click());
  await flush(() => button("创建轻量学习大纲").click());
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
