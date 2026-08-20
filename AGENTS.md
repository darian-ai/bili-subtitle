# Repository Agent Instructions

## 本机网络代理

- 本机 HTTP 代理地址为 `http://127.0.0.1:7890`。
- GitHub、GitHub CLI 或其他外部网络请求出现 `EOF`、`Empty reply from server` 或连接超时时，可为当前 PowerShell 进程临时设置：

```powershell
$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
```

- 使用前可运行 `Test-NetConnection 127.0.0.1 -Port 7890`，确认代理端口正在监听。
- 不要把代理设置写入项目配置或全局 Git 配置；只为确实需要联网的命令临时启用。
- 完成网络操作后，可从当前 PowerShell 会话移除变量：

```powershell
Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
```

- 代理地址不是凭据。仍不得在日志、文档或提交中记录 GitHub token、Cookie 或其他秘密。
