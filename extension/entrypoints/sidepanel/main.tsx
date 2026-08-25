import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./style.css";

const rawTabId = new URLSearchParams(location.search).get("tabId");
const tabId = rawTabId && /^\d+$/.test(rawTabId) ? Number(rawTabId) : undefined;

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{tabId === undefined
    ? <main><h1>bili-study</h1><p role="alert">该侧栏没有绑定视频标签页，请关闭后从视频页重新打开。</p></main>
    : <App tabId={tabId} />}</React.StrictMode>,
);
