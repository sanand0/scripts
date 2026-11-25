@echo off
setlocal DisableDelayedExpansion
rem Let VS Code's IPC CLI resolve paths from the native working directory.
set "PWD="

set "vscode_session="
set "vscode_shared_hook="
set "vscode_saved_hook="
set "vscode_saved_cli="
if defined TMUX for /f "delims=" %%i in ('psmux display-message -p "#{session_name}" 2^>nul') do set "vscode_session=%%i"
if defined vscode_session for /f "tokens=1,* delims==" %%i in ('psmux show-environment -t "%vscode_session%" 2^>nul') do (
    if "%%i"=="VSCODE_IPC_HOOK_CLI" set "vscode_shared_hook=%%j"
    if "%%i"=="VSCODE_CMD_SSH_HOOK" set "vscode_saved_hook=%%j"
    if "%%i"=="VSCODE_CMD_SSH_CLI" set "vscode_saved_cli=%%j"
)

rem Existing panes can have stale hooks. Only use a pipe that still exists.
set "vscode_hook="
for /f "delims=" %%i in ('powershell.exe -NoProfile -Command "$pipes = [IO.Directory]::GetFiles('\\.\pipe\'); foreach ($hook in @($env:VSCODE_IPC_HOOK_CLI, $env:vscode_shared_hook, $env:vscode_saved_hook)) { if ($hook -and $pipes -contains $hook) { $hook; break } }"') do set "vscode_hook=%%i"

rem Call by absolute path so the CLI can locate its node.exe via %%~dp0.
if defined vscode_hook for /f "delims=" %%i in ('where.exe code.cmd 2^>nul') do (
    for %%j in ("%%~dpi.") do if /i "%%~nxj"=="remote-cli" (
        set "vscode_cli=%%i"
        goto launch_remote
    )
)
if defined vscode_hook if defined vscode_saved_cli if exist "%vscode_saved_cli%" (
    set "vscode_cli=%vscode_saved_cli%"
    goto launch_remote
)

if defined vscode_session (
    echo No live VS Code Remote SSH route for this psmux session. Run vscode.cmd from a live VS Code SSH terminal in the session first. 1>&2
    exit /b 1
)

rem Outside psmux, allow the desktop CLI when no Remote SSH route is available.
for /f "delims=" %%i in ('where.exe code.cmd 2^>nul') do (
    for %%j in ("%%~dpi.") do if /i not "%%~nxj"=="remote-cli" (
        set "vscode_cli=%%i"
        goto launch
    )
)

echo VS Code CLI not found on PATH. 1>&2
exit /b 1

:launch_remote
set "VSCODE_IPC_HOOK_CLI=%vscode_hook%"
rem Save separately so a local attach cannot clear the working SSH route.
if defined vscode_session (
    psmux set-environment -t "%vscode_session%" VSCODE_CMD_SSH_HOOK "%vscode_hook%"
    psmux set-environment -t "%vscode_session%" VSCODE_CMD_SSH_CLI "%vscode_cli%"
)

:launch
call "%vscode_cli%" %*
