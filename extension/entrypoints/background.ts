export default defineBackground(() => {
  chrome.action.onClicked.addListener(async (tab) => {
    if (tab.id !== undefined) {
      await chrome.sidePanel.setOptions({
        tabId: tab.id,
        path: `sidepanel.html?tabId=${tab.id}`,
        enabled: true,
      });
      await chrome.sidePanel.open({ tabId: tab.id });
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
