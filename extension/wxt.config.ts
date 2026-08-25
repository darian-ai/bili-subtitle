import { defineConfig } from "wxt";

export default defineConfig({
  modules: ["@wxt-dev/module-react"],
  manifest: {
    name: "bili-study 视频学习",
    description: "连接本机 bili-study 服务的证据化视频学习侧栏",
    version: "0.2.0.0",
    permissions: ["sidePanel", "storage", "tabs"],
    host_permissions: [
      "https://www.bilibili.com/video/*",
      "http://127.0.0.1/*"
    ],
    action: { default_title: "打开 bili-study" },
    side_panel: { default_path: "sidepanel.html" }
  }
});
