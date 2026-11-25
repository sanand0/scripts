@echo off
setlocal
for /f "delims=" %%i in ('psmux show-environment VSCODE_IPC_HOOK_CLI 2^>nul') do set "%%i"
call code.cmd %*
