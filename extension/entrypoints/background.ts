import { sidePanelConfiguration } from "../src/sidepanel-lifecycle";

async function configureTab(tabId: number, url: string | undefined): Promise<void> {
  const options = sidePanelConfiguration(tabId, url);
  await Promise.all([
    chrome.sidePanel.setOptions({
      tabId,
      ...options,
    }),
    options.enabled ? chrome.action.enable(tabId) : chrome.action.disable(tabId),
  ]);
}

export default defineBackground(() => {
  chrome.sidePanel.setOptions({ enabled: false }).catch(() => undefined);
  chrome.action.disable().catch(() => undefined);
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => undefined);

  chrome.tabs.query({}).then((tabs) => Promise.all(
    tabs.flatMap((tab) => tab.id === undefined ? [] : [configureTab(tab.id, tab.url)]),
  )).catch(() => undefined);

  chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.url !== undefined || changeInfo.status === "complete") {
      configureTab(tabId, tab.url).catch(() => undefined);
    }
  });

  chrome.runtime.onMessage.addListener((message, sender) => {
    if (message?.type === "content-video-navigation" && sender.tab?.id !== undefined) {
      configureTab(sender.tab.id, message.context?.supported ? sender.tab.url : undefined)
        .catch(() => undefined);
      chrome.runtime.sendMessage({
        type: "video-navigation",
        tabId: sender.tab.id,
        context: message.context,
      }).catch(() => undefined);
    }
  });
});
