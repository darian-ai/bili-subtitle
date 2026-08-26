import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, DefaultService, OpenAPI, type TranscriptPrepareRequest } from "../../src/api";
import { VideoInspectRequest } from "../../src/api/models/VideoInspectRequest";
import { localApi } from "../../src/local-api";
import { activeChapter, activeCue, type VideoContext } from "../../src/video-context";

interface Library { id: string; name: string }
interface Track { track_id: string; language: string; display_name: string; kind: "human" | "ai" }
interface Inspection {
  source_id: string; bvid: string; page: number; cid: number; title: string;
  video_type: "standard_ugc"; container_type: "standalone" | "ugc_season";
  access_mode: "public" | "entitled"; support_status: "supported" | "conditional";
  limitations: ("current_item_only" | "existing_entitlement_required")[];
  subtitle_status: "available" | "no_subtitles"; tracks: Track[]; inspect_job_id: string;
}
interface Evidence { revision_id?: string; start_cue_id: string; end_cue_id: string }
interface Question {
  question_id: string; text: string; evidence: Evidence; start_ms: number; end_ms: number;
}
interface Chapter {
  chapter_id: string; title: string; summary: string; evidence: Evidence;
  start_ms: number; end_ms: number; questions: Question[];
}
interface DetailItem { text: string; evidence: Evidence }
interface TermItem { term: string; definition: string; evidence: Evidence }
interface ChapterDetail {
  summary: string; summary_evidence: Evidence; key_points: DetailItem[];
  terms: TermItem[]; easy_to_miss: DetailItem[];
}
interface ChapterPractice { questions: Question[] }
interface Feedback { covered: string[]; missing: string[]; misconceptions: string[] }
interface SavedNote {
  note_id: string; revision_id: string; timestamp_ms: number; note_type: string;
  body: string; created_at: string; updated_at: string;
}
interface TranscriptCue { cue_id: string; start_ms: number; end_ms: number; text: string }
interface Transcript {
  revision_id: string; bvid: string; page: number; cid: number; title: string; track_id: string | null;
  language: string; display_name: string; kind: string; content_sha256: string;
  source_verification: "verified" | "legacy_unverified"; page_identity_source: string;
  inspection_job_id?: string | null;
  cues: TranscriptCue[];
}
interface ReflectionAttempt {
  reflection_id: string; guide_id: string; question_id: string; response: string;
  status: "pending" | "succeeded" | "feedback_failed"; feedback?: Feedback | null;
}
interface Guide {
  guide_id: string; revision_id: string; learning_objectives: string[];
  chapters: Chapter[]; details: Record<string, ChapterDetail>;
  practices: Record<string, ChapterPractice>;
}
interface JobProgress { phase: string; percent: number }
interface Job {
  status: "queued" | "running" | "cancel_requested" | "cancelled"
    | "succeeded" | "failed" | "interrupted";
  result?: Record<string, any>; error_code?: string; progress?: JobProgress;
}
type View = { kind: "outline" } | { kind: "chapter"; chapterId: string }
  | { kind: "transcript" } | { kind: "practice" } | { kind: "notes" };
type Pending = "inspect" | "transcript" | "guide" | "detail" | "practice" | "reflection" | "note";
type WorkspaceStatus = "idle" | "loading" | "ready" | "empty" | "error";
interface SessionSnapshot {
  inspection: Inspection | undefined; trackId: string | undefined; guide: Guide | undefined; view: View;
  practiceChapterId: string; note: string; responses: Record<string, string>;
  feedbacks: Record<string, Feedback>; attempts: Record<string, ReflectionAttempt>;
  savedNotes: SavedNote[]; workspaceStatus: WorkspaceStatus;
  transcript: Transcript | undefined; preparedTranscript: Transcript | undefined;
  activeJobId: string | undefined; retryJobId: string | undefined;
  status: string; pending: Pending | undefined;
  jobProgress: { value: JobProgress | undefined; elapsed: number } | undefined;
}

const DEFAULT_ENDPOINT = "http://127.0.0.1:8765";
const PHASES: Record<string, string> = {
  queued: "等待本地任务", starting: "启动任务", fetching_video: "读取视频信息",
  validating_tracks: "检查字幕轨道", fetching_transcript: "下载字幕",
  preparing_outline: "准备轻量大纲", generating_outline: "生成轻量大纲",
  mapping_outline: "分析长字幕", merging_outline: "合并长视频大纲",
  repairing_output: "修复 AI 输出", validating_evidence: "校验证据",
  preparing_chapter: "准备章节", generating_detail: "生成章节详情",
  generating_practice: "生成章节练习", preparing_reflection: "准备证据反馈",
  generating_feedback: "生成证据反馈", publishing: "保存结果",
};
const JOB_ERRORS: Record<string, string> = {
  evidence_validation: "AI 返回的字幕证据无效，自动修复后仍未通过。请重试或更换模型。",
  structure: "AI 返回格式无效，自动修复后仍未通过。请重试或更换模型。",
  subtitle_track_unavailable: "字幕轨道已变化，请重新检查字幕。",
  subtitle_track_ambiguous: "发现多个同名字幕轨道，请重新选择字幕轨道。",
  inspection_source_mismatch: "视频选集已变化，请等待切换完成后重新检查字幕。",
  unsupported_video_type: "当前视频使用不支持的互动、竖屏或特殊播放器。",
  video_not_ready: "视频仍处于首映状态，请在首映结束后重试。",
  video_access_denied: "当前账号无法访问完整视频与字幕。",
  no_subtitles: "当前分集没有可见字幕。",
  subtitle_access_denied: "当前账号无法访问该字幕轨道。",
  bilibili_authentication_required: "Bilibili 登录已失效，请重新登录。",
  authentication: "Provider 认证失败，请检查配置和 API Key。",
  timeout: "Provider 响应超时，请稍后重试。",
  network: "Provider 网络请求失败。",
  quota: "Provider 配额或速率受限。",
};

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { error?: { code?: string; message?: string } } | undefined;
    return body?.error?.message ?? body?.error?.code ?? `Local API ${error.status}`;
  }
  return error instanceof Error ? error.message : "本地服务请求失败。";
}

function jobError(job: Job, prefix: string): Error {
  const code = job.error_code ?? "unknown";
  return new Error(`${prefix}：${JOB_ERRORS[code] ?? code}`);
}

async function currentTabMessage(message: object, boundTabId: number): Promise<any> {
  return chrome.tabs.sendMessage(boundTabId, message);
}

async function waitJob(
  jobId: string,
  update: (progress: JobProgress | undefined, elapsedSeconds: number) => void,
): Promise<Job> {
  const started = Date.now();
  for (;;) {
    const job = await localApi(DefaultService.getJob({ jobId })) as Job;
    update(job.progress, Math.round((Date.now() - started) / 1000));
    if (["succeeded", "failed", "cancelled", "interrupted"].includes(job.status)) return job;
    await new Promise((resolve) => window.setTimeout(resolve, 750));
  }
}

function formatTime(milliseconds: number): string {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function sessionKey(tabId: number, library: string, value: VideoContext): string | undefined {
  return value.supported && value.identity_state !== "transitioning"
    && value.identity_state !== "ambiguous" && value.bvid && value.page && library
    ? JSON.stringify([tabId, library, value.bvid, value.page])
    : undefined;
}

export function App({ tabId }: { tabId: number }) {
  const [endpoint, setEndpoint] = useState(DEFAULT_ENDPOINT);
  const [, setToken] = useState("");
  const [pairCode, setPairCode] = useState("");
  const [connected, setConnected] = useState(false);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [library, setLibrary] = useState("");
  const [provider, setProvider] = useState("");
  const [video, setVideo] = useState<VideoContext>({ supported: false, currentTimeMs: 0 });
  const [inspection, setInspection] = useState<Inspection>();
  const [trackId, setTrackId] = useState<string>();
  const [guide, setGuide] = useState<Guide>();
  const [transcript, setTranscript] = useState<Transcript>();
  const [preparedTranscript, setPreparedTranscript] = useState<Transcript>();
  const [view, setView] = useState<View>({ kind: "outline" });
  const [practiceChapterId, setPracticeChapterId] = useState("");
  const [note, setNote] = useState("");
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [feedbacks, setFeedbacks] = useState<Record<string, Feedback>>({});
  const [attempts, setAttempts] = useState<Record<string, ReflectionAttempt>>({});
  const [savedNotes, setSavedNotes] = useState<SavedNote[]>([]);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatus>("idle");
  const [status, setStatus] = useState("尚未连接本地服务。");
  const [pending, setPending] = useState<Pending>();
  const [activeJobId, setActiveJobId] = useState<string>();
  const [retryJobId, setRetryJobId] = useState<string>();
  const [confirmation, setConfirmation] = useState<{ revision: Transcript; regenerate: boolean }>();
  const [followTranscript, setFollowTranscript] = useState(true);
  const [showGuideTranscript, setShowGuideTranscript] = useState(false);
  const [jobProgress, setJobProgress] = useState<{
    value: JobProgress | undefined; elapsed: number;
  }>();
  const pairing = useRef(false);
  const sourceRequestSequence = useRef(0);
  const operations = useRef(new Set<string>());
  const sessions = useRef(new Map<string, SessionSnapshot>());
  const activeVideoKey = useRef<string | undefined>(undefined);
  const workspaceRequests = useRef({ sequence: 0, latest: new Map<string, number>() });
  const snapshot = useRef<SessionSnapshot>({
    inspection: undefined, trackId: undefined, guide: undefined,
    view: { kind: "outline" }, practiceChapterId: "", note: "", responses: {}, feedbacks: {},
    attempts: {}, savedNotes: [], workspaceStatus: "idle",
    transcript: undefined, preparedTranscript: undefined,
    activeJobId: undefined, retryJobId: undefined,
    status: "尚未连接本地服务。", pending: undefined, jobProgress: undefined,
  });

  useEffect(() => {
    snapshot.current = {
      inspection, trackId, guide, view, practiceChapterId, note, responses, feedbacks,
      attempts, savedNotes, workspaceStatus,
      transcript, preparedTranscript, activeJobId, retryJobId,
      status, pending, jobProgress,
    };
    if (activeVideoKey.current) sessions.current.set(activeVideoKey.current, snapshot.current);
  }, [inspection, trackId, guide, view, practiceChapterId, note, responses, feedbacks,
    attempts, savedNotes, workspaceStatus, transcript, preparedTranscript, activeJobId, retryJobId,
    status, pending, jobProgress]);

  const switchVideo = useCallback((next: VideoContext) => {
    setVideo(next);
  }, []);

  const activeScope = useMemo(() => sessionKey(tabId, library, video), [tabId, library, video]);

  useEffect(() => {
    const previousKey = activeVideoKey.current;
    if (previousKey === activeScope) return;
    if (previousKey) sessions.current.set(previousKey, snapshot.current);
    const saved = activeScope ? sessions.current.get(activeScope) : undefined;
    setInspection(saved?.inspection); setTrackId(saved?.trackId); setGuide(saved?.guide);
    setTranscript(saved?.transcript); setPreparedTranscript(saved?.preparedTranscript);
    setActiveJobId(saved?.activeJobId); setRetryJobId(saved?.retryJobId);
    setConfirmation(undefined); setFollowTranscript(true);
    setShowGuideTranscript(false);
    setView(saved?.view ?? { kind: "outline" });
    setPracticeChapterId(saved?.practiceChapterId ?? ""); setNote(saved?.note ?? "");
    setResponses(saved?.responses ?? {}); setFeedbacks(saved?.feedbacks ?? {});
    setAttempts(saved?.attempts ?? {}); setSavedNotes(saved?.savedNotes ?? []);
    setWorkspaceStatus(saved?.workspaceStatus ?? "idle");
    setPending(saved?.pending); setJobProgress(saved?.jobProgress);
    const inactiveStatus = !video.supported ? "请打开受支持的视频页。"
      : video.identity_state === "transitioning" || video.identity_state === "ambiguous"
        ? "正在确认当前视频分集…"
        : !library ? "请选择知识库。" : "正在读取本地学习记录…";
    setStatus(saved?.status ?? (activeScope ? "正在读取本地学习记录…" : inactiveStatus));
    activeVideoKey.current = activeScope;
  }, [activeScope, library, video.identity_state, video.supported]);

  const configure = useCallback((base: string, bearer: string) => {
    OpenAPI.BASE = base.replace(/\/$/, "");
    OpenAPI.TOKEN = bearer || undefined;
    OpenAPI.HEADERS = { "X-Bili-Study-Origin": chrome.runtime.getURL("").replace(/\/$/, "") };
  }, []);

  const loadLibraries = useCallback(async () => {
    const result = await localApi(DefaultService.listLibraries()) as { libraries: Library[] };
    setLibraries(result.libraries);
    setLibrary((current) => current || result.libraries[0]?.name || "");
  }, []);

  useEffect(() => {
    chrome.storage.local.get(["endpoint", "token", "provider", "library"]).then(async (saved) => {
      const savedEndpoint = typeof saved.endpoint === "string" ? saved.endpoint : DEFAULT_ENDPOINT;
      const savedToken = typeof saved.token === "string" ? saved.token : "";
      setEndpoint(savedEndpoint); setToken(savedToken);
      setProvider(typeof saved.provider === "string" ? saved.provider : "");
      setLibrary(typeof saved.library === "string" ? saved.library : "");
      configure(savedEndpoint, savedToken);
      if (savedToken) {
        try {
          await localApi(DefaultService.health()); await loadLibraries(); setConnected(true);
          setStatus("本地服务已连接。");
        } catch { setStatus("连接已失效，请重新配对。"); }
      }
    });
  }, [configure, loadLibraries]);

  useEffect(() => {
    const refresh = () => {
      const requestId = ++sourceRequestSequence.current;
      return currentTabMessage({ type: "video-context" }, tabId).then((value) => {
        if (requestId === sourceRequestSequence.current && value) {
          switchVideo(value as VideoContext);
        }
      }).catch(() => {
        if (requestId === sourceRequestSequence.current) {
          switchVideo({ supported: false, currentTimeMs: 0 });
        }
      });
    };
    refresh();
    const timer = window.setInterval(refresh, 1000);
    const listener = (message: any) => {
      if (message?.type === "video-navigation"
        && (tabId === undefined || message.tabId === tabId)) {
        sourceRequestSequence.current += 1;
        switchVideo(message.context as VideoContext); refresh();
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => {
      sourceRequestSequence.current += 1;
      window.clearInterval(timer); chrome.runtime.onMessage.removeListener(listener);
    };
  }, [switchVideo, tabId]);

  useEffect(() => { chrome.storage.local.set({ endpoint, provider, library }); }, [endpoint, provider, library]);

  const trackJob = async (
    jobId: string, ownerKey: string | undefined = activeVideoKey.current,
  ): Promise<Job> => {
    if (ownerKey) {
      const saved = sessions.current.get(ownerKey) ?? snapshot.current;
      sessions.current.set(ownerKey, { ...saved, activeJobId: jobId, retryJobId: undefined });
      if (activeVideoKey.current === ownerKey) {
        setActiveJobId(jobId); setRetryJobId(undefined);
      }
    }
    const completed = await waitJob(jobId, (value, elapsed) => {
    const phase = value ? (PHASES[value.phase] ?? value.phase) : "正在处理";
      const nextStatus = `${phase}… 已等待 ${elapsed} 秒`;
      if (!ownerKey || activeVideoKey.current === ownerKey) {
        setJobProgress({ value, elapsed }); setStatus(nextStatus);
      } else {
        const saved = sessions.current.get(ownerKey) ?? snapshot.current;
        sessions.current.set(ownerKey, {
          ...saved, jobProgress: { value, elapsed }, status: nextStatus,
        });
      }
    });
    if (ownerKey) {
      const retryable = completed.status === "failed" || completed.status === "cancelled"
        || completed.status === "interrupted";
      if (activeVideoKey.current === ownerKey) {
        setActiveJobId(undefined); setRetryJobId(retryable ? jobId : undefined);
      } else {
        const saved = sessions.current.get(ownerKey) ?? snapshot.current;
        sessions.current.set(ownerKey, {
          ...saved, activeJobId: undefined, retryJobId: retryable ? jobId : undefined,
        });
      }
    }
    return completed;
  };

  const finishOwner = (ownerKey: string) => {
    if (activeVideoKey.current === ownerKey) {
      setPending(undefined); setJobProgress(undefined);
    } else {
      const saved = sessions.current.get(ownerKey) ?? snapshot.current;
      sessions.current.set(ownerKey, { ...saved, pending: undefined, jobProgress: undefined });
    }
  };

  const stopJob = async () => {
    if (!activeJobId) return;
    try {
      await localApi(DefaultService.cancelJob({ jobId: activeJobId }));
      setStatus("取消中；已发出的 Provider 请求可能仍会产生费用，返回结果将被丢弃。");
    } catch (error) { setStatus(errorText(error)); }
  };

  const retryJob = async () => {
    if (!retryJobId) return;
    setStatus("正在显式重试原任务…");
    try {
      const accepted = await localApi(DefaultService.retryJob({ jobId: retryJobId }));
      const job = await trackJob(accepted.job_id);
      if (job.status !== "succeeded") throw jobError(job, "重试失败");
      setStatus("重试任务已完成，请重新加载当前页面内容。");
      if (activeVideoKey.current && video.bvid && video.page) {
        await loadWorkspace(activeVideoKey.current, video.bvid, video.page, library);
      }
    } catch (error) { setStatus(errorText(error)); }
  };

  const fetchWorkspace = async (
    bvid: string, page: number, libraryName: string,
  ): Promise<{ guide?: Guide; notes: SavedNote[]; reflections: ReflectionAttempt[]; transcript?: Transcript } | undefined> => {
    const lookup = await localApi(DefaultService.getVideoWorkspace({
      bvid, page, library: libraryName,
    }));
    if (lookup.bvid !== bvid || lookup.page !== page) {
      throw new Error("workspace 返回了不属于请求 BV/P 的结果。");
    }
    if (!lookup.guide_id && !lookup.revision_id) return undefined;
    if (lookup.guide_id) return fetchGuideWorkspace(lookup.guide_id, libraryName, bvid, page);
    const savedTranscript = await localApi(DefaultService.getTranscript({
      revisionId: lookup.revision_id!, library: libraryName,
    })) as Transcript;
    if (savedTranscript.bvid !== bvid || savedTranscript.page !== page) {
      throw new Error("workspace Transcript 不属于请求 BV/P。");
    }
    return { notes: [], reflections: [], transcript: savedTranscript };
  };

  const fetchGuideWorkspace = async (
    guideId: string, libraryName: string, expectedBvid?: string, expectedPage?: number,
  ) => {
    const workspace = await localApi(DefaultService.getStudyGuideWorkspace({
      guideId, library: libraryName,
    })) as unknown as { guide: Guide; notes: SavedNote[]; reflections: ReflectionAttempt[] };
    const savedTranscript = await localApi(DefaultService.getTranscript({
      revisionId: workspace.guide.revision_id, library: libraryName,
    })) as Transcript;
    if ((expectedBvid !== undefined && savedTranscript.bvid !== expectedBvid)
      || (expectedPage !== undefined && savedTranscript.page !== expectedPage)) {
      throw new Error("guide workspace Transcript 不属于请求 BV/P。");
    }
    return { ...workspace, transcript: savedTranscript };
  };

  const applyWorkspace = (
    ownerKey: string,
    workspace: { guide?: Guide; notes: SavedNote[]; reflections: ReflectionAttempt[]; transcript?: Transcript } | undefined,
  ) => {
    const owner = JSON.parse(ownerKey) as [number, string, string, number];
    const expectedBvid = owner[2]; const expectedPage = owner[3];
    if (workspace?.transcript
      && (workspace.transcript.bvid !== expectedBvid || workspace.transcript.page !== expectedPage)) {
      throw new Error("拒绝应用不属于当前 BV/P 的 workspace。");
    }
    if (workspace?.guide && workspace.transcript?.revision_id !== workspace.guide.revision_id) {
      throw new Error("拒绝应用指南与字幕 revision 不一致的 workspace。");
    }
    const latestAttempts: Record<string, ReflectionAttempt> = {};
    const restoredFeedbacks: Record<string, Feedback> = {};
    const restoredResponses: Record<string, string> = {};
    for (const attempt of workspace?.reflections ?? []) {
      latestAttempts[attempt.question_id] = attempt;
      restoredResponses[attempt.question_id] = attempt.response;
      if (attempt.status === "succeeded" && attempt.feedback) {
        restoredFeedbacks[attempt.question_id] = attempt.feedback;
      }
    }
    const nextStatus: WorkspaceStatus = workspace ? "ready" : "empty";
    const nextMessage = workspace?.guide
      ? "已加载该视频上次保存的学习内容。"
      : workspace?.transcript
        ? "已加载本地字幕；该视频尚未创建学习大纲。"
      : "当前知识库中没有该视频的学习记录。";
    if (activeVideoKey.current === ownerKey) {
      setGuide(workspace?.guide); setTranscript(workspace?.transcript);
      setSavedNotes(workspace?.notes ?? []);
      setAttempts(latestAttempts); setWorkspaceStatus(nextStatus); setStatus(nextMessage);
      setResponses((current) => ({ ...restoredResponses, ...current }));
      setFeedbacks(restoredFeedbacks);
    } else {
      const saved = sessions.current.get(ownerKey) ?? snapshot.current;
      sessions.current.set(ownerKey, {
        ...saved, guide: workspace?.guide, transcript: workspace?.transcript,
        savedNotes: workspace?.notes ?? [],
        attempts: latestAttempts, responses: { ...restoredResponses, ...saved.responses },
        feedbacks: restoredFeedbacks, workspaceStatus: nextStatus, status: nextMessage,
      });
    }
  };

  const loadWorkspace = async (
    ownerKey: string, bvid: string, page: number, libraryName: string,
  ) => {
    const requestId = ++workspaceRequests.current.sequence;
    workspaceRequests.current.latest.set(ownerKey, requestId);
    if (activeVideoKey.current === ownerKey) setWorkspaceStatus("loading");
    try {
      const workspace = await fetchWorkspace(bvid, page, libraryName);
      if (workspaceRequests.current.latest.get(ownerKey) === requestId) {
        applyWorkspace(ownerKey, workspace);
      }
      return workspace;
    } catch (error) {
      if (workspaceRequests.current.latest.get(ownerKey) === requestId
        && activeVideoKey.current === ownerKey) {
        setWorkspaceStatus("error");
        setStatus(`读取已有学习记录失败：${errorText(error)}`);
      }
      throw error;
    }
  };

  useEffect(() => {
    if (!connected || !library || !video.bvid || !video.page || !activeScope) return;
    void loadWorkspace(activeScope, video.bvid, video.page, library).catch(() => undefined);
  }, [connected, activeScope]);

  const pair = async () => {
    if (pairing.current) return;
    pairing.current = true;
    let tokenIssued = false;
    setPending("inspect"); setStatus("正在配对…"); configure(endpoint, "");
    try {
      const response = await localApi(DefaultService.pair({ requestBody: { code: pairCode } }));
      tokenIssued = true; setToken(response.token); configure(endpoint, response.token);
      await chrome.storage.local.set({ endpoint, token: response.token });
      await loadLibraries(); setConnected(true); setPairCode(""); setStatus("配对成功。");
    } catch (error) {
      setConnected(false);
      setStatus(tokenIssued ? `配对成功，但连接初始化失败：${errorText(error)}` : errorText(error));
    } finally { pairing.current = false; setPending(undefined); }
  };

  const prepareTrack = async (checked: Inspection, track: Track, ownerKey: string) => {
    const operationId = `transcript:${ownerKey}`;
    if (operations.current.has(operationId)) return undefined;
    operations.current.add(operationId);
    const ownerLibrary = library;
    try {
      if (activeVideoKey.current === ownerKey) {
        setPending("transcript"); setStatus("正在加载并保存字幕时间轴…");
      }
      const accepted = await localApi(DefaultService.prepareTranscript({
        bvid: checked.bvid, page: checked.page,
        requestBody: {
          library: ownerLibrary, inspect_job_id: checked.inspect_job_id,
          track_id: track.track_id, track_language: track.language,
          track_display_name: track.display_name,
          track_kind: track.kind as TranscriptPrepareRequest.track_kind,
        },
      }));
      const job = await trackJob(accepted.job_id, ownerKey);
      if (job.status !== "succeeded") throw jobError(job, "字幕加载失败");
      if (job.result?.bvid !== checked.bvid || job.result?.page !== checked.page) {
        throw new Error("字幕任务返回了不属于当前分集的结果。");
      }
      const loaded = await localApi(DefaultService.getTranscript({
        revisionId: String(job.result.revision_id), library: ownerLibrary,
      })) as Transcript;
      if (loaded.bvid !== checked.bvid || loaded.page !== checked.page) {
        throw new Error("字幕 revision 与当前分集不匹配。");
      }
      if (activeVideoKey.current === ownerKey) {
        setPreparedTranscript(loaded); setShowGuideTranscript(false);
        setStatus("字幕已加载，可在字幕页查看。");
      } else {
        const saved = sessions.current.get(ownerKey) ?? snapshot.current;
        sessions.current.set(ownerKey, {
          ...saved, preparedTranscript: loaded, status: "字幕已加载，可在字幕页查看。",
        });
      }
      return loaded;
    } finally {
      operations.current.delete(operationId);
      finishOwner(ownerKey);
    }
  };

  const inspect = async () => {
    const ownerKey = activeVideoKey.current;
    const expectedBvid = video.bvid; const expectedPage = video.page;
    if (!expectedBvid || !expectedPage || !library || !ownerKey
      || video.identity_state === "transitioning" || video.identity_state === "ambiguous") return;
    const operationId = `inspect:${ownerKey}`;
    if (operations.current.has(operationId)) return;
    operations.current.add(operationId);
    setPending("inspect"); setJobProgress(undefined); setStatus("正在检查视频与字幕轨道…");
    try {
      const accepted = await localApi(DefaultService.inspectVideo({ requestBody: {
        library, bvid: expectedBvid, page: expectedPage,
        identity_state: "resolved", identity_evidence: (video.identity_evidence === "url_page"
          ? VideoInspectRequest.identity_evidence.URL_PAGE
          : video.identity_evidence === "video_pod_page"
            ? VideoInspectRequest.identity_evidence.VIDEO_POD_PAGE
          : video.identity_evidence === "video_pod_item"
            ? VideoInspectRequest.identity_evidence.VIDEO_POD_ITEM
            : VideoInspectRequest.identity_evidence.SINGLE_VIDEO),
        ...(video.collection_index === undefined ? {} : { collection_index: video.collection_index }),
        ...(video.collection_total === undefined ? {} : { collection_total: video.collection_total }),
      } }));
      const job = await trackJob(accepted.job_id, ownerKey);
      if (job.status !== "succeeded") throw jobError(job, "检查失败");
      const result = { ...(job.result as unknown as Inspection), inspect_job_id: accepted.job_id };
      if (result.bvid !== expectedBvid || result.page !== expectedPage) {
        throw new Error("检查任务返回了不属于启动分集的结果。");
      }
      const firstTrack = result.tracks[0];
      if (activeVideoKey.current === ownerKey) {
        setInspection(result); setTrackId(firstTrack?.track_id); setPreparedTranscript(undefined);
        setStatus(result.subtitle_status === "no_subtitles"
          ? "当前分集没有可见字幕。"
          : result.support_status === "conditional"
            ? `已有账号权限可用，发现 ${result.tracks.length} 条字幕轨道。`
            : `发现 ${result.tracks.length} 条字幕轨道。`);
      } else {
        const saved = sessions.current.get(ownerKey) ?? snapshot.current;
        sessions.current.set(ownerKey, {
          ...saved, inspection: result, trackId: firstTrack?.track_id,
          preparedTranscript: undefined,
        });
      }
      if (result.tracks.length === 1 && firstTrack) await prepareTrack(result, firstTrack, ownerKey);
    } catch (error) {
      if (activeVideoKey.current === ownerKey) setStatus(errorText(error));
    } finally { operations.current.delete(operationId); finishOwner(ownerKey); }
  };

  const generateGuide = async (regenerate = false, confirmed = false) => {
    const operationKey = activeVideoKey.current;
    if (!operationKey || !video.bvid || !video.page || !library) return;
    if (!regenerate) {
      if (guide) { setView({ kind: "outline" }); setStatus("已显示保存的学习大纲。"); return; }
      try {
        const existing = await loadWorkspace(operationKey, video.bvid, video.page, library);
        if (existing?.guide) { setView({ kind: "outline" }); return; }
      } catch { return; }
    }
    const selectedRevision = confirmed ? confirmation?.revision : (preparedTranscript ?? transcript);
    if (!selectedRevision || !provider) {
      setStatus("首次生成需要先加载字幕并填写 Provider。");
      return;
    }
    if (!confirmed) { setConfirmation({ revision: selectedRevision, regenerate }); return; }
    const ownerLibrary = library;
    setConfirmation(undefined);
    setPending("guide"); setJobProgress(undefined); setStatus("正在生成轻量大纲…");
    try {
      const accepted = await localApi(DefaultService.createStudyGuide({ requestBody: {
        library: ownerLibrary, provider, revision_id: selectedRevision.revision_id,
        expected_bvid: selectedRevision.bvid, expected_page: selectedRevision.page, regenerate,
      } }));
      const job = await trackJob(accepted.job_id, operationKey);
      if (job.status !== "succeeded") throw jobError(job, "生成失败");
      if (job.result?.bvid !== selectedRevision.bvid || job.result?.page !== selectedRevision.page
        || job.result?.revision_id !== selectedRevision.revision_id) {
        throw new Error("生成任务返回了不属于确认来源的结果。");
      }
      const generated = await fetchGuideWorkspace(
        String(job.result?.guide_id), ownerLibrary, selectedRevision.bvid, selectedRevision.page,
      );
      applyWorkspace(operationKey, generated);
      if (activeVideoKey.current === operationKey) {
        setPracticeChapterId(""); setView({ kind: "outline" }); setStatus("轻量学习大纲已就绪。");
      }
    } catch (error) {
      const failedStatus = errorText(error);
      if (activeVideoKey.current === operationKey) setStatus(failedStatus);
      else {
        const saved = sessions.current.get(operationKey) ?? snapshot.current;
        sessions.current.set(operationKey, { ...saved, status: failedStatus });
      }
    } finally {
      finishOwner(operationKey);
    }
  };

  const loadDetail = async (chapterId: string) => {
    const ownerKey = activeVideoKey.current;
    if (!guide || !ownerKey || !video.bvid || !video.page) return;
    const ownerGuideId = guide.guide_id; const ownerLibrary = library;
    try {
      const existing = await loadWorkspace(ownerKey, video.bvid, video.page, ownerLibrary);
      if (existing?.guide?.details[chapterId]) return;
    } catch { return; }
    if (!provider) { setStatus("生成新章节详情需要填写 Provider。"); return; }
    setPending("detail"); setJobProgress(undefined); setStatus("正在按需生成章节详情…");
    try {
      const accepted = await localApi(DefaultService.createChapterDetail({
        guideId: ownerGuideId, chapterId, requestBody: { library: ownerLibrary, provider },
      }));
      const job = await trackJob(accepted.job_id, ownerKey);
      if (job.status !== "succeeded") throw jobError(job, "详情失败");
      if (job.result?.bvid !== video.bvid || job.result?.page !== video.page
        || job.result?.revision_id !== guide.revision_id) {
        throw new Error("详情任务返回了不属于启动来源的结果。");
      }
      applyWorkspace(ownerKey, await fetchGuideWorkspace(ownerGuideId, ownerLibrary));
      if (activeVideoKey.current === ownerKey) setStatus("章节详情已保存。");
    } catch (error) { if (activeVideoKey.current === ownerKey) setStatus(errorText(error)); }
    finally { finishOwner(ownerKey); }
  };

  const loadPractice = async (chapterId: string) => {
    const ownerKey = activeVideoKey.current;
    if (!guide || !ownerKey || !video.bvid || !video.page) return;
    const ownerGuideId = guide.guide_id; const ownerLibrary = library;
    try {
      const existing = await loadWorkspace(ownerKey, video.bvid, video.page, ownerLibrary);
      if (existing?.guide?.practices[chapterId]) return;
    } catch { return; }
    if (!provider) { setStatus("生成新章节练习需要填写 Provider。"); return; }
    setPending("practice"); setJobProgress(undefined); setStatus("正在生成本章练习…");
    try {
      const accepted = await localApi(DefaultService.createChapterPractice({
        guideId: ownerGuideId, chapterId, requestBody: { library: ownerLibrary, provider },
      }));
      const job = await trackJob(accepted.job_id, ownerKey);
      if (job.status !== "succeeded") throw jobError(job, "练习生成失败");
      if (job.result?.bvid !== video.bvid || job.result?.page !== video.page
        || job.result?.revision_id !== guide.revision_id) {
        throw new Error("练习任务返回了不属于启动来源的结果。");
      }
      applyWorkspace(ownerKey, await fetchGuideWorkspace(ownerGuideId, ownerLibrary));
      if (activeVideoKey.current === ownerKey) setStatus("本章练习已就绪。");
    } catch (error) { if (activeVideoKey.current === ownerKey) setStatus(errorText(error)); }
    finally { finishOwner(ownerKey); }
  };

  const saveNote = async () => {
    const ownerKey = activeVideoKey.current;
    if (!guide || !note.trim() || !ownerKey) return;
    const ownerGuideId = guide.guide_id; const ownerLibrary = library;
    setPending("note");
    try {
      await localApi(DefaultService.createNote({ requestBody: {
        library: ownerLibrary, source_id: guide.revision_id, timestamp_ms: video.currentTimeMs, body: note,
      } }));
      applyWorkspace(ownerKey, await fetchGuideWorkspace(ownerGuideId, ownerLibrary));
      if (activeVideoKey.current === ownerKey) { setNote(""); setStatus("个人笔记已独立保存为 Markdown。"); }
    } catch (error) { if (activeVideoKey.current === ownerKey) setStatus(errorText(error)); }
    finally { finishOwner(ownerKey); }
  };

  const reflect = async (questionId: string) => {
    const ownerKey = activeVideoKey.current;
    const response = responses[questionId]?.trim();
    if (!guide || !response || !ownerKey || !video.bvid || !video.page) return;
    const ownerGuideId = guide.guide_id; const ownerLibrary = library;
    try {
      const existing = await loadWorkspace(ownerKey, video.bvid, video.page, ownerLibrary);
      const matched = [...(existing?.reflections ?? [])].reverse().find((attempt) =>
        attempt.question_id === questionId && attempt.response === response
        && attempt.status === "succeeded" && attempt.feedback);
      if (matched?.feedback) {
        if (activeVideoKey.current === ownerKey) {
          setFeedbacks((current) => ({ ...current, [questionId]: matched.feedback! }));
          setStatus("已显示原先保存的证据反馈。");
        }
        return;
      }
    } catch { return; }
    if (!provider) { setStatus("生成新反馈需要填写 Provider。"); return; }
    setPending("reflection"); setJobProgress(undefined); setStatus("正在依据字幕证据评阅…");
    try {
      const accepted = await localApi(DefaultService.createReflection({ requestBody: {
        library: ownerLibrary, provider, guide_id: ownerGuideId, question_id: questionId,
        response,
      } }));
      const job = await trackJob(accepted.job_id, ownerKey);
      if (job.status !== "succeeded") throw jobError(job, "反馈失败");
      if (job.result?.bvid !== video.bvid || job.result?.page !== video.page
        || job.result?.revision_id !== guide.revision_id) {
        throw new Error("反馈任务返回了不属于启动来源的结果。");
      }
      applyWorkspace(ownerKey, await fetchGuideWorkspace(ownerGuideId, ownerLibrary));
      if (activeVideoKey.current === ownerKey) setStatus("证据反馈已生成。");
    } catch (error) { if (activeVideoKey.current === ownerKey) setStatus(errorText(error)); }
    finally { finishOwner(ownerKey); }
  };

  const highlighted = useMemo(
    () => guide ? activeChapter(guide.chapters, video.currentTimeMs) : undefined,
    [guide, video.currentTimeMs],
  );
  const selectedTranscript = showGuideTranscript ? transcript : (preparedTranscript ?? transcript);
  const displayedTranscript = selectedTranscript !== undefined && selectedTranscript.bvid === video.bvid
    && selectedTranscript.page === video.page ? selectedTranscript : undefined;
  const displayedSourceAttested = displayedTranscript?.source_verification === "verified"
    && Boolean(displayedTranscript.inspection_job_id);
  const currentCue = useMemo(
    () => activeCue(displayedTranscript?.cues ?? [], video.currentTimeMs),
    [displayedTranscript, video.currentTimeMs],
  );
  const transcriptList = useRef<HTMLOListElement>(null);
  const automaticScroll = useRef(false);
  useEffect(() => {
    if (view.kind !== "transcript" || !followTranscript || !currentCue) return;
    automaticScroll.current = true;
    const currentElement = transcriptList.current
      ?.querySelector<HTMLElement>(`[data-cue-id="${currentCue.cue_id}"]`);
    if (typeof currentElement?.scrollIntoView === "function") {
      currentElement.scrollIntoView({ block: "center" });
    }
    window.setTimeout(() => { automaticScroll.current = false; }, 0);
  }, [view.kind, followTranscript, currentCue?.cue_id]);
  const seek = (timestampMs: number) => currentTabMessage({ type: "seek", timestampMs }, tabId)
    .catch(() => setStatus("无法跳转播放器。"));
  const selectedChapter = view.kind === "chapter"
    ? guide?.chapters.find((chapter) => chapter.chapter_id === view.chapterId) : undefined;
  const selectedDetail = selectedChapter ? guide?.details[selectedChapter.chapter_id] : undefined;
  const selectedPracticeId = practiceChapterId || guide?.chapters[0]?.chapter_id || "";
  const selectedPracticeChapter = guide?.chapters.find((chapter) => chapter.chapter_id === selectedPracticeId);
  const selectedPractice = selectedPracticeChapter
    ? guide?.practices[selectedPracticeChapter.chapter_id]
      ?? (selectedPracticeChapter.questions.length ? { questions: selectedPracticeChapter.questions } : undefined)
    : undefined;

  return <main>
    <header><h1>bili-study</h1><span className={connected ? "online" : "offline"}>{connected ? "已连接" : "未连接"}</span></header>
    <p className="status" role="status">{status}</p>
    {connected && activeScope && workspaceStatus === "loading" && <p className="muted-text">正在读取本地学习记录…</p>}
    {connected && activeScope && workspaceStatus === "error" && <button className="quiet" onClick={() => {
      if (video.bvid && video.page) void loadWorkspace(activeScope, video.bvid, video.page, library).catch(() => undefined);
    }}>重试加载已有内容</button>}
    {jobProgress && <div className="progress" aria-label="任务进度">
      <div><span>{PHASES[jobProgress.value?.phase ?? ""] ?? "正在处理"}</span><span>{jobProgress.value?.percent ?? 0}%</span></div>
      <progress max="100" value={jobProgress.value?.percent ?? 0} />
      {activeJobId && <button className="quiet compact" onClick={stopJob}>停止任务</button>}
    </div>}
    {!activeJobId && retryJobId && <button className="quiet" onClick={retryJob}>重试上次任务</button>}

    {!connected && <section><h2>连接本地服务</h2>
      <label>地址<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} /></label>
      <label>配对码<input value={pairCode} onChange={(event) => setPairCode(event.target.value.toUpperCase())} placeholder="运行 bili-study plugin pair" /></label>
      <button disabled={Boolean(pending) || !pairCode} onClick={pair}>配对</button>
    </section>}

    {connected && view.kind === "outline" && <>
      <section className={!video.supported ? "muted" : ""}><h2>当前视频</h2>
        {!video.supported ? <p>请打开受支持的普通 Bilibili 视频页。</p> : <>
          {video.identity_state === "transitioning" || video.identity_state === "ambiguous"
            ? <p>播放器正在切换选集，来源尚未稳定，请稍候。</p>
            : <p><code>{video.bvid}</code> · {video.identity_evidence === "video_pod_item"
              && video.collection_index !== undefined && video.collection_total !== undefined
              ? `合集第 ${video.collection_index} / ${video.collection_total} 项 · ` : ""}
              P{video.page} · {formatTime(video.currentTimeMs)}</p>}
          <label>知识库<select value={library} onChange={(event) => setLibrary(event.target.value)}>{libraries.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
          <label>Provider<input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="已配置的名称" /></label>
          <button disabled={Boolean(pending) || !library || !activeScope} onClick={inspect}>检查字幕</button>
        </>}
      </section>
      {inspection && <section><h2>字幕轨道</h2>
        <p>{inspection.container_type === "ugc_season" ? "UGC 合集当前项" : "普通 UGC"}{inspection.access_mode === "entitled" ? " · 已有权限" : ""}</p>
        {inspection.tracks.length === 0 ? <p>当前分集没有可见字幕。</p> : <>
        <select value={trackId} onChange={(event) => setTrackId(event.target.value)}>{inspection.tracks.map((track) => <option key={track.track_id} value={track.track_id}>{track.display_name} · {track.kind}</option>)}</select>
        <button disabled={Boolean(pending) || !trackId} onClick={() => {
          const selected = inspection.tracks.find((item) => item.track_id === trackId);
          if (selected && activeVideoKey.current) {
            void prepareTrack(inspection, selected, activeVideoKey.current)
              .catch((error) => setStatus(errorText(error)));
          }
        }}>加载字幕</button>
        {(preparedTranscript || (!guide && transcript)) && <button disabled={Boolean(pending) || workspaceStatus === "loading"} onClick={() => generateGuide(false)}>创建轻量学习大纲</button>}
      </>}</section>}
      {preparedTranscript && guide && preparedTranscript.revision_id !== guide.revision_id && <section>
        <h2>待生成版本</h2><p>P{preparedTranscript.page} · {preparedTranscript.title} · {preparedTranscript.display_name} · <code>{preparedTranscript.revision_id}</code></p>
      </section>}
      {confirmation && <section className="confirmation" aria-label="生成确认">
        <h2>确认发送字幕</h2>
        <p>P{confirmation.revision.page} · {confirmation.revision.title}</p>
        <p>{confirmation.revision.display_name} · {confirmation.revision.kind} · revision <code>{confirmation.revision.revision_id}</code></p>
        <p>Provider：{provider}</p>
        <p className="muted-text">确认后才会把这份字幕发送给 Provider；价格未知时无法估算费用。</p>
        <div className="row"><button onClick={() => generateGuide(confirmation.regenerate, true)}>确认并开始</button><button className="quiet" onClick={() => setConfirmation(undefined)}>取消</button></div>
      </section>}
      {guide && <section><div className="row"><h2>学习大纲</h2><button className="quiet compact" disabled={Boolean(pending)} onClick={() => generateGuide(true)}>重新生成</button></div>
        <ul>{guide.learning_objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>
        <div className="chapter-list">{guide.chapters.map((chapter) => <button key={chapter.chapter_id} className={`chapter-card ${highlighted?.chapter_id === chapter.chapter_id ? "active" : ""}`} onClick={() => setView({ kind: "chapter", chapterId: chapter.chapter_id })}>
          <span className="chapter-heading"><strong>{chapter.title}</strong><span>{formatTime(chapter.start_ms)}</span></span>
          <span>{chapter.summary}</span>
        </button>)}</div>
      </section>}
    </>}

    {connected && view.kind === "chapter" && selectedChapter && <section className="page">
      <button className="back" onClick={() => setView({ kind: "outline" })}>← 返回大纲</button>
      <div className="row"><h2>{selectedChapter.title}</h2><button className="quiet compact" onClick={() => seek(selectedChapter.start_ms)}>{formatTime(selectedChapter.start_ms)}</button></div>
      <p>{selectedChapter.summary}</p>
      {selectedDetail
        ? <DetailView detail={selectedDetail} onSeek={() => seek(selectedChapter.start_ms)} />
        : <button disabled={Boolean(pending) || workspaceStatus === "loading"} onClick={() => loadDetail(selectedChapter.chapter_id)}>生成本章详情</button>}
    </section>}

    {connected && view.kind === "transcript" && <section className="page transcript-page"><div className="row"><h2>字幕</h2>
      {!followTranscript && <button className="quiet compact" onClick={() => setFollowTranscript(true)}>回到当前字幕</button>}
    </div>
      {!displayedTranscript ? <p>请先加载字幕。</p> : <>
        {guide && preparedTranscript && preparedTranscript.revision_id !== transcript?.revision_id && <div className="row" aria-label="字幕版本">
          <button className={!showGuideTranscript ? "compact" : "quiet compact"} onClick={() => setShowGuideTranscript(false)}>新加载字幕</button>
          <button className={showGuideTranscript ? "compact" : "quiet compact"} onClick={() => setShowGuideTranscript(true)}>指南绑定字幕</button>
        </div>}
        <p className="muted-text">P{displayedTranscript.page} · {displayedTranscript.title} · {displayedTranscript.display_name} · revision <code>{displayedTranscript.revision_id}</code></p>
        <p className="muted-text">来源：<code>{displayedTranscript.bvid}</code> / P{displayedTranscript.page} / CID {displayedTranscript.cid}
          {displayedTranscript.inspection_job_id && <> / inspect <code>{displayedTranscript.inspection_job_id}</code></>}
          {` / ${displayedSourceAttested ? "服务端已验证" : "来源链不完整"}`}</p>
        <p className="muted-text">内容 SHA-256：<code>{displayedTranscript.content_sha256}</code></p>
        {!displayedSourceAttested && <p className="warning">这份历史字幕缺少完整来源证明，请重新检查并加载字幕后再使用。</p>}
        <ol ref={transcriptList} className="transcript-list" aria-label="完整字幕时间轴" onScroll={() => {
          if (!automaticScroll.current) setFollowTranscript(false);
        }}>{displayedTranscript.cues.map((cue) => <li key={cue.cue_id} data-cue-id={cue.cue_id} className={cue.cue_id === currentCue?.cue_id ? "current" : ""}>
          <button className="cue" onClick={() => seek(cue.start_ms)} aria-current={cue.cue_id === currentCue?.cue_id ? "true" : undefined}>
            <time>{formatTime(cue.start_ms)}</time><span>{cue.text}</span>
          </button>
        </li>)}</ol>
      </>}
    </section>}

    {connected && view.kind === "practice" && <section className="page"><h2>按章练习</h2>
      {!guide ? <p>请先在大纲页创建学习大纲。</p> : <>
        <label>选择章节<select value={selectedPracticeId} onChange={(event) => setPracticeChapterId(event.target.value)}>{guide.chapters.map((chapter) => <option key={chapter.chapter_id} value={chapter.chapter_id}>{chapter.title}</option>)}</select></label>
        {selectedPracticeChapter && <p className="muted-text">{selectedPracticeChapter.summary}</p>}
        {!selectedPractice && selectedPracticeChapter && <button disabled={Boolean(pending) || workspaceStatus === "loading"} onClick={() => loadPractice(selectedPracticeChapter.chapter_id)}>生成本章练习</button>}
        {selectedPractice?.questions.map((question) => <div className="question" key={question.question_id}><p>{question.text}</p>
          <textarea value={responses[question.question_id] ?? ""} onChange={(event) => setResponses({ ...responses, [question.question_id]: event.target.value })} placeholder="回答或复述" />
          <div className="row"><button disabled={Boolean(pending) || !responses[question.question_id]?.trim()} onClick={() => reflect(question.question_id)}>获取证据反馈</button><button className="quiet" onClick={() => seek(question.start_ms)}>回看证据</button></div>
          {attempts[question.question_id]?.status === "feedback_failed" && <p className="muted-text">上次回答已保存，但反馈生成失败，可以重试。</p>}
          {feedbacks[question.question_id] && <FeedbackView feedback={feedbacks[question.question_id]!} />}
        </div>)}
      </>}
    </section>}

    {connected && view.kind === "notes" && <section className="page"><h2>时间戳笔记</h2>
      {!guide ? <p>请先创建学习大纲。</p> : <>
        <p>当前视频位置：{formatTime(video.currentTimeMs)}</p>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录当前时刻的想法" />
        <button disabled={Boolean(pending) || !note.trim()} onClick={saveNote}>保存个人笔记</button>
        {savedNotes.length > 0 && <><h3>已保存笔记</h3><ul>{savedNotes.map((item) =>
          <li key={item.note_id}><button className="quiet compact" onClick={() => seek(item.timestamp_ms)}>{formatTime(item.timestamp_ms)}</button> {item.body}</li>
        )}</ul></>}
      </>}
    </section>}

    {connected && <nav aria-label="学习功能">
      <button className={view.kind === "outline" || view.kind === "chapter" ? "selected" : ""} onClick={() => setView({ kind: "outline" })}>大纲</button>
      <button className={view.kind === "transcript" ? "selected" : ""} onClick={() => setView({ kind: "transcript" })}>字幕</button>
      <button className={view.kind === "practice" ? "selected" : ""} onClick={() => setView({ kind: "practice" })}>练习</button>
      <button className={view.kind === "notes" ? "selected" : ""} onClick={() => setView({ kind: "notes" })}>笔记</button>
    </nav>}
  </main>;
}

function DetailView({ detail, onSeek }: { detail: ChapterDetail; onSeek: () => void }) {
  return <div className="detail">
    <h3>本章总结</h3><p>{detail.summary}</p>
    {detail.key_points.length > 0 && <><h3>关键点</h3><ul>{detail.key_points.map((item) => <li key={item.text}>{item.text}</li>)}</ul></>}
    {detail.terms.length > 0 && <><h3>术语</h3><dl>{detail.terms.map((item) => <div key={item.term}><dt>{item.term}</dt><dd>{item.definition}</dd></div>)}</dl></>}
    {detail.easy_to_miss.length > 0 && <><h3>容易遗漏</h3><ul>{detail.easy_to_miss.map((item) => <li key={item.text}>{item.text}</li>)}</ul></>}
    <button className="quiet" onClick={onSeek}>回看本章证据</button>
  </div>;
}

function FeedbackView({ feedback }: { feedback: Feedback }) {
  return <div className="feedback">
    {feedback.covered.length > 0 && <><h3>已经覆盖</h3><ul>{feedback.covered.map((item) => <li key={item}>{item}</li>)}</ul></>}
    {feedback.missing.length > 0 && <><h3>可以补充</h3><ul>{feedback.missing.map((item) => <li key={item}>{item}</li>)}</ul></>}
    {feedback.misconceptions.length > 0 && <><h3>可能的误解</h3><ul>{feedback.misconceptions.map((item) => <li key={item}>{item}</li>)}</ul></>}
  </div>;
}
