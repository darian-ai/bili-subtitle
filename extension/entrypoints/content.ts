import { readVideoDomSnapshot } from "../src/bilibili-dom";
import { resolveVideoContext } from "../src/video-context";

function context() {
  return resolveVideoContext(
    location.href,
    document.querySelector<HTMLVideoElement>("video")?.currentTime ?? 0,
    readVideoDomSnapshot(document),
  );
}

export default defineContentScript({
  matches: ["https://www.bilibili.com/video/*"],
  main(contentContext) {
    const onMessage = (message: any, _sender: chrome.runtime.MessageSender,
      sendResponse: (response?: any) => void) => {
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
    };
    chrome.runtime.onMessage.addListener(onMessage);

    let previous = "";
    let scheduled: number | undefined;
    const notifyNavigation = () => {
      if (!contentContext.isValid || scheduled !== undefined) return;
      scheduled = contentContext.setTimeout(() => {
        scheduled = undefined;
        if (!contentContext.isValid) return;
        const next = context();
        const fingerprint = JSON.stringify({
          supported: next.supported, bvid: next.bvid, page: next.page,
          identity_state: next.identity_state, identity_evidence: next.identity_evidence,
          collection_index: next.collection_index, collection_total: next.collection_total,
        });
        if (previous === fingerprint) return;
        previous = fingerprint;
        try {
          chrome.runtime.sendMessage({ type: "content-video-navigation", context: next })
            .catch(() => undefined);
        } catch {
          // Extension reload invalidates the old isolated world synchronously.
        }
      }, 100);
    };
    contentContext.addEventListener(window, "popstate", notifyNavigation);
    const observer = new MutationObserver(notifyNavigation);
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true,
      attributeFilter: ["class", "content", "data-cid", "data-key", "href"] });
    contentContext.onInvalidated(() => {
      observer.disconnect();
      try { chrome.runtime.onMessage.removeListener(onMessage); } catch { /* already invalid */ }
    });
    notifyNavigation();
  }
});
