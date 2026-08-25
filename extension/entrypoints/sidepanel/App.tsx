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
interface Evidence { revision_id: string; start_cue_id: string; end_cue_id: string }
interface Question { question_id: string; text: string; evidence: Evidence; start_ms: number; end_ms: number }
interface Chapter {
  chapter_id: string; title: string; summary: string; evidence: Evidence;
  start_ms: number; end_ms: number; questions: Question[];
}
interface Guide {
  guide_id: string; revision_id: string; learning_objectives: string[];
  chapters: Chapter[]; details: Record<string, unknown>;
}
interface Job { status: "queued" | "running" | "succeeded" | "failed"; result?: Record<string, any>; error_code?: string }

const DEFAULT_ENDPOINT = "http://127.0.0.1:8765";

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { error?: { code?: string; message?: string } } | undefined;
    return body?.error?.message ?? body?.error?.code ?? `Local API ${error.status}`;
  }
  return error instanceof Error ? error.message : "本地服务请求失败。";
}

async function currentTabMessage(message: object): Promise<any> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return undefined;
  return chrome.tabs.sendMessage(tab.id, message);
}

async function waitJob(jobId: string, update: (text: string) => void): Promise<Job> {
  for (;;) {
    const job = await localApi(DefaultService.getJob({ jobId })) as Job;
    update(job.status === "queued" ? "等待本地 worker…" : "正在处理…");
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((resolve) => window.setTimeout(resolve, 750));
  }
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
  const [note, setNote] = useState("");
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("尚未连接本地服务。");
  const [busy, setBusy] = useState(false);
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
        try { await localApi(DefaultService.health()); await loadLibraries(); setConnected(true); setStatus("本地服务已连接。"); }
        catch { setStatus("连接已失效，请重新配对。"); }
      }
    });
  }, [configure, loadLibraries]);

  useEffect(() => {
    const refresh = () => currentTabMessage({ type: "video-context" }).then((value) => {
      if (value) setVideo(value as VideoContext);
    }).catch(() => setVideo({ supported: false, currentTimeMs: 0 }));
    refresh();
    const timer = window.setInterval(refresh, 1000);
    const listener = (message: any) => { if (message?.type === "video-navigation") { setInspection(undefined); setGuide(undefined); refresh(); } };
    chrome.runtime.onMessage.addListener(listener);
    return () => { window.clearInterval(timer); chrome.runtime.onMessage.removeListener(listener); };
  }, []);

  useEffect(() => { chrome.storage.local.set({ endpoint, provider, library }); }, [endpoint, provider, library]);

  const pair = async () => {
    if (pairing.current) return;
    pairing.current = true;
    let tokenIssued = false;
    setBusy(true); setStatus("正在配对…"); configure(endpoint, "");
    try {
      const response = await localApi(DefaultService.pair({ requestBody: { code: pairCode } }));
      tokenIssued = true;
      setToken(response.token); configure(endpoint, response.token);
      await chrome.storage.local.set({ endpoint, token: response.token });
      await loadLibraries(); setConnected(true); setPairCode(""); setStatus("配对成功。");
    } catch (error) {
      setConnected(false);
      setStatus(tokenIssued ? `配对成功，但连接初始化失败：${errorText(error)}` : errorText(error));
    } finally {
      pairing.current = false;
      setBusy(false);
    }
  };

  const inspect = async () => {
    if (!video.bvid || !video.page || !library) return;
    setBusy(true); setStatus("正在检查视频与字幕轨道…");
    try {
      const accepted = await localApi(DefaultService.inspectVideo({ requestBody: { library, bvid: video.bvid, page: video.page } }));
      const job = await waitJob(accepted.job_id, setStatus);
      if (job.status === "failed") throw new Error(`检查失败：${job.error_code ?? "unknown"}`);
      const result = job.result as unknown as Inspection;
      setInspection(result); setTrackId(result.tracks[0]?.track_id); setGuide(undefined);
      setStatus(result.subtitle_status === "no_subtitles" ? "当前分集没有可见字幕。" : `发现 ${result.tracks.length} 条字幕轨道。`);
    } catch (error) { setStatus(errorText(error)); }
    finally { setBusy(false); }
  };

  const generateGuide = async (regenerate = false) => {
    if (!inspection || trackId === undefined || !library || !provider) return;
    setBusy(true); setStatus("正在生成学习大纲…");
    try {
      const accepted = await localApi(DefaultService.createStudyGuide({ requestBody: {
        library, provider, bvid: inspection.bvid, page: inspection.page, cid: inspection.cid,
        title: inspection.title, track_id: trackId, regenerate
      }}));
      const job = await waitJob(accepted.job_id, setStatus);
      if (job.status === "failed") throw new Error(`生成失败：${job.error_code ?? "unknown"}`);
      const guideId = String(job.result?.guide_id);
      setGuide(await localApi(DefaultService.getStudyGuide({ guideId, library })) as unknown as Guide);
      setStatus("学习大纲已就绪。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setBusy(false); }
  };

  const loadDetail = async (chapterId: string) => {
    if (!guide) return;
    setBusy(true); setStatus("正在按需生成章节详情…");
    try {
      const accepted = await localApi(DefaultService.createChapterDetail({ guideId: guide.guide_id, chapterId, requestBody: { library, provider } }));
      const job = await waitJob(accepted.job_id, setStatus);
      if (job.status === "failed") throw new Error(`详情失败：${job.error_code ?? "unknown"}`);
      setGuide(await localApi(DefaultService.getStudyGuide({ guideId: guide.guide_id, library })) as unknown as Guide);
      setStatus("章节详情已保存。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setBusy(false); }
  };

  const saveNote = async () => {
    if (!guide || !note.trim()) return;
    setBusy(true);
    try {
      await localApi(DefaultService.createNote({ requestBody: { library, source_id: guide.revision_id, timestamp_ms: video.currentTimeMs, body: note } }));
      setNote(""); setStatus("个人笔记已独立保存为 Markdown。");
    } catch (error) { setStatus(errorText(error)); }
    finally { setBusy(false); }
  };

  const reflect = async (questionId: string) => {
    if (!guide || !responses[questionId]?.trim()) return;
    setBusy(true); setStatus("正在依据字幕证据评阅…");
    try {
      const accepted = await localApi(DefaultService.createReflection({ requestBody: { library, provider, guide_id: guide.guide_id, question_id: questionId, response: responses[questionId] } }));
      const job = await waitJob(accepted.job_id, setStatus);
      if (job.status === "failed") throw new Error(`反馈失败：${job.error_code ?? "unknown"}`);
      setStatus(`反馈：${JSON.stringify(job.result?.feedback)}`);
    } catch (error) { setStatus(errorText(error)); }
    finally { setBusy(false); }
  };

  const highlighted = useMemo(() => guide ? activeChapter(guide.chapters, video.currentTimeMs) : undefined, [guide, video.currentTimeMs]);
  const seek = (timestampMs: number) => currentTabMessage({ type: "seek", timestampMs }).catch(() => setStatus("无法跳转播放器。"));

  return <main>
    <header><h1>bili-study</h1><span className={connected ? "online" : "offline"}>{connected ? "已连接" : "未连接"}</span></header>
    <p className="status" role="status">{status}</p>
    {!connected && <section><h2>连接本地服务</h2>
      <label>地址<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} /></label>
      <label>配对码<input value={pairCode} onChange={(event) => setPairCode(event.target.value.toUpperCase())} placeholder="运行 bili-study plugin pair" /></label>
      <button disabled={busy || !pairCode} onClick={pair}>配对</button>
    </section>}
    {connected && <>
      <section className={!video.supported ? "muted" : ""}><h2>当前视频</h2>
        {!video.supported ? <p>请打开受支持的普通 Bilibili 视频页。</p> : <><p><code>{video.bvid}</code> · P{video.page} · {Math.round(video.currentTimeMs / 1000)}s</p>
          <label>知识库<select value={library} onChange={(event) => setLibrary(event.target.value)}>{libraries.map((item) => <option key={item.id}>{item.name}</option>)}</select></label>
          <label>Provider<input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="已配置的名称" /></label>
          <button disabled={busy || !library} onClick={inspect}>检查字幕</button></>}
      </section>
      {inspection && <section><h2>字幕轨道</h2>{inspection.tracks.length === 0 ? <p>无字幕；这不是认证或访问失败。</p> : <>
        <select value={trackId} onChange={(event) => setTrackId(event.target.value)}>{inspection.tracks.map((track) => <option key={track.track_id} value={track.track_id}>{track.display_name} · {track.kind}</option>)}</select>
        <button disabled={busy || !provider} onClick={() => generateGuide(false)}>创建学习指南</button></>}
      </section>}
      {guide && <><section><div className="row"><h2>学习大纲</h2><button className="quiet" disabled={busy} onClick={() => generateGuide(true)}>重新生成 AI 内容</button></div>
        <ul>{guide.learning_objectives.map((objective) => <li key={objective}>{objective}</li>)}</ul>
        {guide.chapters.map((chapter) => <article key={chapter.chapter_id} className={highlighted?.chapter_id === chapter.chapter_id ? "active" : ""}>
          <button className="chapter" onClick={() => seek(chapter.start_ms)}><strong>{chapter.title}</strong><span>{Math.round(chapter.start_ms / 1000)}s</span></button>
          <p>{chapter.summary}</p>
          {guide.details[chapter.chapter_id] ? <pre>{JSON.stringify(guide.details[chapter.chapter_id], null, 2)}</pre> : <button disabled={busy} onClick={() => loadDetail(chapter.chapter_id)}>按需生成详情</button>}
          {chapter.questions.map((question) => <div className="question" key={question.question_id}><p>{question.text}</p>
            <textarea value={responses[question.question_id] ?? ""} onChange={(event) => setResponses({ ...responses, [question.question_id]: event.target.value })} placeholder="回答或复述" />
            <div className="row"><button disabled={busy || !responses[question.question_id]?.trim()} onClick={() => reflect(question.question_id)}>获取证据反馈</button><button className="quiet" onClick={() => seek(question.start_ms)}>回看证据</button></div>
          </div>)}
        </article>)}</section>
        <section><h2>时间戳笔记</h2><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={`记录 ${Math.round(video.currentTimeMs / 1000)}s 的想法`} /><button disabled={busy || !note.trim()} onClick={saveNote}>保存个人笔记</button></section>
      </>}
    </>}
  </main>;
}
