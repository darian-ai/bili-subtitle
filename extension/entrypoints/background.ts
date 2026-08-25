export default defineBackground(() => {
  chrome.action.onClicked.addListener((tab) => {
    if (tab.id !== undefined) {
      const configuring = chrome.sidePanel.setOptions({
        tabId: tab.id,
        path: `sidepanel.html?tabId=${tab.id}`,
        enabled: true,
      });
      // open() must be invoked synchronously inside the click callback. Awaiting
      // setOptions first causes Chrome to discard the user-activation token.
      const opening = chrome.sidePanel.open({ tabId: tab.id });
      Promise.all([configuring, opening]).catch((error: unknown) => {
        console.error("无法打开 bili-study 侧栏。", error);
      });
    }
  });
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => undefined);

  chrome.runtime.onMessage.addListener((message, sender) => {
    if (message?.type === "content-video-navigation" && sender.tab?.id !== undefined) {
      chrome.runtime.sendMessage({
        type: "video-navigation",
        tabId: sender.tab.id,
        context: message.context,
      }).catch(() => undefined);
    }
  });
});
