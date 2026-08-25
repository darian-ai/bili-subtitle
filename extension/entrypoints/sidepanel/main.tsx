import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./style.css";

const rawTabId = new URLSearchParams(location.search).get("tabId");
const tabId = rawTabId && /^\d+$/.test(rawTabId) ? Number(rawTabId) : undefined;

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App {...(tabId === undefined ? {} : { tabId })} /></React.StrictMode>,
);
