import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, DefaultService, OpenAPI } from "../../src/api";
import { localApi } from "../../src/local-api";
import { activeChapter, type VideoContext } from "../../src/video-context";

interface Library { id: string; name: string }
interface Track { track_id: string; language: string; display_name: string; kind: "human" | "ai" }
interface Inspection {
  source_id: string; bvid: string; page: number; cid: number; title: string;
  subtitle_status: "available" | "no_subtitles"; tracks: Track[];
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
interface Guide {
  guide_id: string; revision_id: string; learning_objectives: string[];
  chapters: Chapter[]; details: Record<string, ChapterDetail>;
  practices: Record<string, ChapterPractice>;
}
interface JobProgress { phase: string; percent: number }
interface Job {
  status: "queued" | "running" | "succeeded" | "failed";
  result?: Record<string, any>; error_code?: string; progress?: JobProgress;
}
type View = { kind: "outline" } | { kind: "chapter"; chapterId: string }
  | { kind: "practice" } | { kind: "notes" };
type Pending = "inspect" | "guide" | "detail" | "practice" | "reflection" | "note";

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

async function currentTabMessage(message: object): Promise<any> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return undefined;
  return chrome.tabs.sendMessage(tab.id, message);
}

async function waitJob(
  jobId: string,
  update: (progress: JobProgress | undefined, elapsedSeconds: number) => void,
): Promise<Job> {
  const started = Date.now();
  for (;;) {
    const job = await localApi(DefaultService.getJob({ jobId })) as Job;
    update(job.progress, Math.round((Date.now() - started) / 1000));
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((resolve) => window.setTimeout(resolve, 750));
  }
}

function formatTime(milliseconds: number): string {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function App() {
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
  const [view, setView] = useState<View>({ kind: "outline" });
  const [practiceChapterId, setPracticeChapterId] = useState("");
  const [note, setNote] = useState("");
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [feedbacks, setFeedbacks] = useState<Record<string, Feedback>>({});
  const [status, setStatus] = useState("尚未连接本地服务。");
  const [pending, setPending] = useState<Pending>();
  const [jobProgress, setJobProgress] = useState<{
    value: JobProgress | undefined; elapsed: number;
  }>();
  const pairing = useRef(false);

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
    const refresh = () => currentTabMessage({ type: "video-context" }).then((value) => {
      if (value) setVideo(value as VideoContext);
    }).catch(() => setVideo({ supported: false, currentTimeMs: 0 }));
    refresh();
    const timer = window.setInterval(refresh, 1000);
    const listener = (message: any) => {
      if (message?.type === "video-navigation") {
        setInspection(undefined); setGuide(undefined); setView({ kind: "outline" }); refresh();
      }
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => { window.clearInterval(timer); chrome.runtime.onMessage.removeListener(listener); };
  }, []);

  useEffect(() => { chrome.storage.local.set({ endpoint, provider, library }); }, [endpoint, provider, library]);

  const trackJob = async (jobId: string): Promise<Job> => waitJob(jobId, (value, elapsed) => {
    setJobProgress({ value, elapsed });
    const phase = value ? (PHASES[value.phase] ?? value.phase) : "正在处理";
    setStatus(`${phase}… 已等待 ${elapsed} 秒`);
  });

  const refreshGuide = async (guideId: string) => {
    setGuide(await localApi(DefaultService.getStudyGuide({ guideId, library })) as unknown as Guide);
  };

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

  const inspect = async () => {
    if (!video.bvid || !video.page || !library) return;
    setPending("inspect"); setJobProgress(undefined); setStatus("正在检查视频与字幕轨道…");
    try {
      const accepted = await localApi(DefaultService.inspectVideo({ requestBody: {
        library, bvid: video.bvid, page: video.page,
      } }));
      const job = await trackJob(accepted.job_id);
      if (job.status === "failed") throw jobError(job, "检查失败");
      const result = job.result as unknown as Inspection;
      setInspection(result); setTrackId(result.tracks[0]?.track_id); setGuide(undefined);
      setStatus(result.subtitle_status === "no_subtitles" ? "当前分集没有可见字幕。" : `发现 ${result.tracks.length} 条字幕轨道。`);
    } catch (error) { setStatus(errorText(error)); }
    finally { setPending(undefined); setJobProgress(undefined); }
  };

  const generateGuide = async (regenerate = false) => {
    if (!inspection || trackId === undefined || !library || !provider) return;
    setPending("guide"); setJobProgress(undefined); setStatus("正在生成轻量大纲…");
    try {
      const accepted = await localApi(DefaultService.createStudyGuide({ requestBody: {
        library, provider, bvid: inspection.bvid, page: inspection.page, cid: inspection.cid,
        title: inspection.title, track_id: trackId, regenerate,
      } }));
      const job = await trackJob(accepted.job_id);
      if (job.status === "failed") throw jobError(job, "生成失败");
      const guideId = String(job.result?.guide_id);
      await refreshGuide(guideId); setPracticeChapterId(""); setView({ kind: "outline" });
      setStatus("轻量学习大纲已就绪。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setPending(undefined); setJobProgress(undefined); }
  };

  const loadDetail = async (chapterId: string) => {
    if (!guide) return;
    setPending("detail"); setJobProgress(undefined); setStatus("正在按需生成章节详情…");
    try {
      const accepted = await localApi(DefaultService.createChapterDetail({
        guideId: guide.guide_id, chapterId, requestBody: { library, provider },
      }));
      const job = await trackJob(accepted.job_id);
      if (job.status === "failed") throw jobError(job, "详情失败");
      await refreshGuide(guide.guide_id); setStatus("章节详情已保存。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setPending(undefined); setJobProgress(undefined); }
  };

  const loadPractice = async (chapterId: string) => {
    if (!guide) return;
    setPending("practice"); setJobProgress(undefined); setStatus("正在生成本章练习…");
    try {
      const accepted = await localApi(DefaultService.createChapterPractice({
        guideId: guide.guide_id, chapterId, requestBody: { library, provider },
      }));
      const job = await trackJob(accepted.job_id);
      if (job.status === "failed") throw jobError(job, "练习生成失败");
      await refreshGuide(guide.guide_id); setStatus("本章练习已就绪。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setPending(undefined); setJobProgress(undefined); }
  };

  const saveNote = async () => {
    if (!guide || !note.trim()) return;
    setPending("note");
    try {
      await localApi(DefaultService.createNote({ requestBody: {
        library, source_id: guide.revision_id, timestamp_ms: video.currentTimeMs, body: note,
      } }));
      setNote(""); setStatus("个人笔记已独立保存为 Markdown。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setPending(undefined); }
  };

  const reflect = async (questionId: string) => {
    if (!guide || !responses[questionId]?.trim()) return;
    setPending("reflection"); setJobProgress(undefined); setStatus("正在依据字幕证据评阅…");
    try {
      const accepted = await localApi(DefaultService.createReflection({ requestBody: {
        library, provider, guide_id: guide.guide_id, question_id: questionId,
        response: responses[questionId],
      } }));
      const job = await trackJob(accepted.job_id);
      if (job.status === "failed") throw jobError(job, "反馈失败");
      setFeedbacks({ ...feedbacks, [questionId]: job.result?.feedback as unknown as Feedback });
      setStatus("证据反馈已生成。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setPending(undefined); setJobProgress(undefined); }
  };

  const highlighted = useMemo(
    () => guide ? activeChapter(guide.chapters, video.currentTimeMs) : undefined,
    [guide, video.currentTimeMs],
  );
  const seek = (timestampMs: number) => currentTabMessage({ type: "seek", timestampMs })
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
    {jobProgress && <div className="progress" aria-label="任务进度">
      <div><span>{PHASES[jobProgress.value?.phase ?? ""] ?? "正在处理"}</span><span>{jobProgress.value?.percent ?? 0}%</span></div>
      <progress max="100" value={jobProgress.value?.percent ?? 0} />
    </div>}

    {!connected && <section><h2>连接本地服务</h2>
      <label>地址<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} /></label>
      <label>配对码<input value={pairCode} onChange={(event) => setPairCode(event.target.value.toUpperCase())} placeholder="运行 bili-study plugin pair" /></label>
      <button disabled={Boolean(pending) || !pairCode} onClick={pair}>配对</button>
    </section>}

    {connected && view.kind === "outline" && <>
      <section className={!video.supported ? "muted" : ""}><h2>当前视频</h2>
        {!video.supported ? <p>请打开受支持的普通 Bilibili 视频页。</p> : <>
          <p><code>{video.bvid}</code> · P{video.page} · {formatTime(video.currentTimeMs)}</p>
          <label>知识库<select value={library} onChange={(event) => setLibrary(event.target.value)}>{libraries.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
          <label>Provider<input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="已配置的名称" /></label>
          <button disabled={Boolean(pending) || !library} onClick={inspect}>检查字幕</button>
        </>}
      </section>
      {inspection && <section><h2>字幕轨道</h2>{inspection.tracks.length === 0 ? <p>当前分集没有可见字幕。</p> : <>
        <select value={trackId} onChange={(event) => setTrackId(event.target.value)}>{inspection.tracks.map((track) => <option key={track.track_id} value={track.track_id}>{track.display_name} · {track.kind}</option>)}</select>
        <button disabled={Boolean(pending) || !provider} onClick={() => generateGuide(false)}>创建轻量学习大纲</button>
      </>}</section>}
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
        : <button disabled={Boolean(pending) || !provider} onClick={() => loadDetail(selectedChapter.chapter_id)}>生成本章详情</button>}
    </section>}

    {connected && view.kind === "practice" && <section className="page"><h2>按章练习</h2>
      {!guide ? <p>请先在大纲页创建学习大纲。</p> : <>
        <label>选择章节<select value={selectedPracticeId} onChange={(event) => setPracticeChapterId(event.target.value)}>{guide.chapters.map((chapter) => <option key={chapter.chapter_id} value={chapter.chapter_id}>{chapter.title}</option>)}</select></label>
        {selectedPracticeChapter && <p className="muted-text">{selectedPracticeChapter.summary}</p>}
        {!selectedPractice && selectedPracticeChapter && <button disabled={Boolean(pending) || !provider} onClick={() => loadPractice(selectedPracticeChapter.chapter_id)}>生成本章练习</button>}
        {selectedPractice?.questions.map((question) => <div className="question" key={question.question_id}><p>{question.text}</p>
          <textarea value={responses[question.question_id] ?? ""} onChange={(event) => setResponses({ ...responses, [question.question_id]: event.target.value })} placeholder="回答或复述" />
          <div className="row"><button disabled={Boolean(pending) || !responses[question.question_id]?.trim()} onClick={() => reflect(question.question_id)}>获取证据反馈</button><button className="quiet" onClick={() => seek(question.start_ms)}>回看证据</button></div>
          {feedbacks[question.question_id] && <FeedbackView feedback={feedbacks[question.question_id]!} />}
        </div>)}
      </>}
    </section>}

    {connected && view.kind === "notes" && <section className="page"><h2>时间戳笔记</h2>
      {!guide ? <p>请先创建学习大纲。</p> : <>
        <p>当前视频位置：{formatTime(video.currentTimeMs)}</p>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="记录当前时刻的想法" />
        <button disabled={Boolean(pending) || !note.trim()} onClick={saveNote}>保存个人笔记</button>
      </>}
    </section>}

    {connected && <nav aria-label="学习功能">
      <button className={view.kind === "outline" || view.kind === "chapter" ? "selected" : ""} onClick={() => setView({ kind: "outline" })}>大纲</button>
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
