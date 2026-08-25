import { parseVideoContext } from "../src/video-context";

function context() {
  return parseVideoContext(location.href, document.querySelector<HTMLVideoElement>("video")?.currentTime ?? 0);
}

export default defineContentScript({
  matches: ["https://www.bilibili.com/video/*"],
  main() {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (message?.type === "video-context") {
        sendResponse(context());
      }
      if (message?.type === "seek" && typeof message.timestampMs === "number") {
        const video = document.querySelector<HTMLVideoElement>("video");
        if (video) {
          video.currentTime = Math.max(0, message.timestampMs / 1000);
          sendResponse({ ok: true, currentTimeMs: Math.round(video.currentTime * 1000) });
        } else {
          sendResponse({ ok: false });
        }
      }
      return true;
    });

    let previous = location.href;
    const notifyNavigation = () => {
      if (previous !== location.href) {
        previous = location.href;
        chrome.runtime.sendMessage({ type: "content-video-navigation", context: context() }).catch(() => undefined);
      }
    };
    window.addEventListener("popstate", notifyNavigation);
    const observer = new MutationObserver(notifyNavigation);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
});
