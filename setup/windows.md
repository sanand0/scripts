# Windows

Here is the setup for my Windows laptops.

# Plutonium, 18 Jul 2023

Sager NP7881E laptop - Windows 11.

- GeForce RTX 4070 8GB GDDR6
- 144Hz 17.3 inches Thin Bezel Full HD (1920 x 1080)
- 13th Gen Intel Core i9-13900HX 24-Core Processor, 36MB Cache, up to 5.4GHz Turbo Boost
- Ram: 32GB DDR5 4800MHz
- Storage: 1TB PCIe Gen4 NVMe SSD

Setup:

- Start with Local Account with name "Anand", not a remote account
- Uninstall useless apps like Solitaire, Instagram, LinkedIn, WhatsApp, Messenger, etc.
- [Change folder locations](https://answers.microsoft.com/en-us/windows/forum/all/configuring-folder-locations-in-windows-10/7974a938-9b84-4bd0-a6ab-e50d1fcd0822) to `C:\` instead of `C:\Users\Anand\`
- Uninstall Teams (personal). [Install Teams for work or school](https://www.microsoft.com/en-in/microsoft-teams/download-app#for-desktop)
- Install non-portable software:
  - MS Office
  - [VSCode](https://code.visualstudio.com/) + Sync settings
  - [Dropbox](https://dropbox.com/) + Sync folders
  - [Cygwin](https://www.cygwin.com/) with ssh, nano, make
  - [Mamba](https://mamba.readthedocs.io/en/latest/)
  - [Everything Lite](https://www.voidtools.com/)
  - FortiClient VPN
  - Minecraft from Windows Store
  - [OBS](https://obsproject.com/)
  - [VLC](https://www.videolan.org/vlc/)
- Install via WinGet: `winget install --id AutoHotkey.AutoHotkey 7zip.7zip Cisco.ClamAV dotPDNLLC.paintdotnet NickeManarin.ScreenToGif calibre.calibre Microsoft.PowerToys SQLiteStudio Zoom.Zoom`
- Install portable apps under `C:\Apps\` for folder access:
  - [Git](https://git-scm.com/downloads/win) + [LFS](https://git-lfs.com/)
  - [NodeJS](https://nodejs.org/en/download)
- Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install)
- In Admin PowerShell, run `wsl --install -d Ubuntu` to install WSL 2 + Ubuntu
  - Use "sudo passwd -d `whoami`" to remove password
- Install [Docker in Ubuntu](https://docs.docker.com/engine/install/ubuntu/). See [docker-wsl.md](docker-wsl.md#install-docker-on-wsl-2)
- Install [NVIDIA Container Toolkit in WSL](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). See [docker-wsl.md](docker-wsl.md#install-docker-on-wsl-2-with-gpu)
- [Disable lock screen on display timeout](https://www.groovypost.com/howto/disable-the-lock-screen-on-windows-11/)
- [X-Mouse](https://winaero.com/enable-xmouse-window-tracking-windows-10/). Use [ActiveWndTrkTimeout](https://stackoverflow.com/a/35172720/100904)
- Configure Everything
  - Exclude filter `*.pyc;*.pyo;*.pyc;*.dll;*.pyi;*.c;*.h;*.hpp;*.manifest;*.map;*.cat;*.mum;*.mui;*.ts;*.sip;*.fzp;*.po;*.tcl;*.so;*.mum;*.cat;*.mui;*.cdf-ms`
  - Exclude folders filter: `__pycache__`
  - node_modules, .git, .vscode
  - Enable Search > Match Path
- Configure VS Code
  - VS Code needs Git for Windows. It can't handle Cygwin paths. In VS Code settings.json, add `"git.path": "C:\\Apps\\git\\bin\\git.exe"`
- Add shortcut to C:\Anand\Main\autohotkey.ahk to [shell:startup](http://support.microsoft.com/kb/2806079)

Skip installing:

- MongoDB, ElasticSearch: I rarely use them any more
- Redis, QGIS: install when required
- InkScape: It's quite bad
- XAMPP: Use Caddy instead

# Titanium, 11 Jul 2022

[Lenovo ThinkPad X11](https://pcsupport.lenovo.com/sg/en/products/laptops-and-netbooks/thinkpad-p-series-laptops/thinkpad-p15s-gen-2-type-20w6-20w7/20w7/20w7s0gd00/pf2t55qf) running Windows 11.

- Swap Fn and Ctrl on ThinkPad keyboard
- Uninstall Lenovo Quick Clean to disable Fn + Right Shift shortcut
- Download latest Audio driver for Windows 11 from Lenovo website
- [Change folder locations](https://answers.microsoft.com/en-us/windows/forum/all/configuring-folder-locations-in-windows-10/7974a938-9b84-4bd0-a6ab-e50d1fcd0822)
- [Remove OneDrive personal](https://answers.microsoft.com/en-us/msoffice/forum/all/how-to-remove-onedrive-personal/22de5a90-7651-43c3-b14b-6bc222602796)
- Disable personal Teams by preventing launch at startup from Add/Remove programs
- [Disable lock screen on display timeout](https://www.groovypost.com/howto/disable-the-lock-screen-on-windows-11/)
- [X-Mouse](https://winaero.com/enable-xmouse-window-tracking-windows-10/). Use [ActiveWndTrkTimeout](https://stackoverflow.com/a/35172720/100904)
- Chrome + Sync settings
- VSCode + Sync settings
- Dropbox + Sync folders
- Set up [Windows Phone Link](https://www.microsoft.com/en-us/windows/sync-across-your-devices)
- [Cygwin](https://www.cygwin.com/) with ssh, nano, make
- Install Anaconda
- Install MS Office
- Install non-portable software: Everything Lite, Glassbrick, MechVibes, Office, Minecraft, Paint.NET, Power BI, PowerToys
- Install software, portable/otherwise: Audacity, AutoHotkey, 7-Zip, OBS, QGIS, InkScape, VLC
- Install/Copy Portable Apps: Git, Git LFS, XAMPP, NodeJS, ElasticSearch, MongoDB, Redis, PostgreSQL, blender, libreoffice, krita
- Add shortcut to C:\Anand\Main\autohotkey.ahk to [shell:startup](http://support.microsoft.com/kb/2806079)
- In Admin PowerShell, run `wsl --install -d Ubuntu` to install WSL 2 + Ubuntu
  - Use "sudo passwd -d `whoami`" to remove password
- Everything: Exclude filter `*.pyc;*.pyo;*.pyc;*.dll;*.pyi;*.c;*.h;*.hpp;*.manifest;*.map;*.cat;*.mum;*.mui;*.ts;*.sip;*.fzp;*.po;*.tcl;*.so;*.mum;*.cat;*.mui;*.cdf-ms`
- Skip: SyncIOS

# Windows 8.1 setup

- [Optional Microsoft accounts](http://blogs.technet.com/b/pauljones/archive/2013/10/07/windows-8-1-mail-app-without-microsoft-account.aspx)
- Disk cleanup: [delete EVERYTHING](http://windows.microsoft.com/en-IN/windows-8/how-remove-windows-old-folder)
- [X-Mouse](http://winaero.com/blog/turn-on-xmouse-active-window-tracking-focus-follows-mouse-pointer-feature-in-windows-8-1-windows-8-and-windows-7/)
- Redirect [default folder](http://windows.microsoft.com/en-in/windows/redirect-folder-new-location) locations
- Remove [lock screen image](http://www.guidingtech.com/25160/change-windows-8-1-lock-screen-remove/)
- Install [Inconsolata](http://levien.com/type/myfonts/inconsolata.html)
- Chrome should not look [blurred](http://www.howtogeek.com/175664/how-to-make-the-windows-desktop-work-well-on-high-dpi-displays-and-fix-blurry-fonts/)
  nor have [touch optimised UI](https://productforums.google.com/forum/#!searchin/chrome/omnibox$20suggestions$20blank/chrome/Fdt2SLpuZxE/HkJBBOUNbRMJ)
- [Speed up Windows Explorer](http://superuser.com/a/667014)
- Add [AutoHotkey](http://ahkscript.org/download/) to [shell:startup](http://support.microsoft.com/kb/2806079)
- [Show libraries](http://windows.microsoft.com/en-in/windows/libraries-faq)
- [Dell drivers](http://en.community.dell.com/support-forums/laptop/w/laptop/4195.xps-l502x-windows-8-64-bit.aspx)
  - [Touchpad](http://downloads-us.dell.com/FOLDER00800134M/2/): requires .Net 3.5
  - [BIOS drivers](http://ftp1.dell.com/folder00950861m/1/)
  - [Audio](http://ftp1.dell.com/folder00952236m/13/)
  - [NVidia](http://ftp1.dell.com/folder00793600m/7/)
- Run Windows Update and get optional video drivers to speed up Office menus.

# Folder shortcuts

Map D: to C: if you're using only 1 drive. Run `SUBST D: C:\` [on startup](https://superuser.com/a/1266753/446702)

Create hard links for shortcuts:

```shell
CD C:\
MKLINK /J C:\site\gramener.com\viz C:\viz
```

```shell
cd /
ln -s /cygdrive/c
ln -s /cygdrive/d
ln -s /cygdrive/d/site/gramener.com/viz
```

# X-Mouse settings

- [How to make mouse in Windows 7 act the same as Windows XP](https://superuser.com/q/76315/446702)
- [X-Mouse Controls](https://joelpurra.com/projects/X-Mouse_Controls/)
- [X-Mouse on Windows 10](https://winaero.com/enable-xmouse-window-tracking-windows-10/)

# Windows Utilities

Essentials

- 7zip.7zip
- [Everything](http://www.voidtools.com/)
- [PowerToys](https://docs.microsoft.com/en-us/windows/powertoys/)
- [Paint.NET](http://www.getpaint.net/) image editor
- [Screen to GIF](http://www.screentogif.com/) for animated GIF screen capture
- [AutoHotKey](https://www.autohotkey.com/)
- [Calibre](http://calibre-ebook.com/) ebook reader
- [SQLiteStudio](https://sqlitestudio.pl/) to view SQLite databases
- [qbittorrent](https://www.qbittorrent.org/) to download torrents
- [gitleaks](https://gitleaks.io/) to detect password leaks in git repos
- [caddy](https://caddyserver.com/) HTTP server
- [ngrok](https://ngrok.com/) HTTP tunnel
- [rclone](https://rclone.org/) to sync with Google Drive, OneDrive, etc.

Useful

- [Equalizer APO](https://equalizerapo.com/) increases audio 7 (In Configurator > Troubleshooting Options > Install as SFX/EFX - Experimental)
- [Audacity](http://audacity.sourceforge.net/) audio editor
- [VLC](http://www.videolan.org/vlc/index.html) media player
- [mp3tag](https://www.mp3tag.de/en/) Portable to edit MP3 tags
- [pandoc](https://pandoc.org/) to convert between document formats (Word, markdown, etc.)
- [Open Broadcast Studio](https://obsproject.com/) for video recording
- [WizTree](https://www.diskanalyzer.com/) for disk monitoring usage
- [ffmpeg](https://www.ffmpeg.org/) to convert audio/video formats
- [Putty](https://www.putty.org) for SFTP
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download from YouTube instead of youtube-dl

Unused but fine

- [keyviz](https://github.com/mulaRahul/keyviz) to display keystrokes
- [Carnac](https://github.com/Code52/carnac/) to display keystrokes
- [MechVibes](https://github.com/hainguyents13/mechvibes/) to produce mechanical keyboard sounds
- [RainMeter](https://www.rainmeter.net/) for desktop widgets
- [Iriun](https://iriun.com) portable for mobile camera
- [Mermaid](https://mermaid.js.org/) to create diagrams from text. See [Text to diagram tools](https://xosh.org/text-to-diagram/)
- QGIS
- XAMPP

Avoid / deprecated

- [Postman](https://postman.com/) - use Edge/Chrome Devtools Network Console instead
- [gInk](https://github.com/geovens/gInk): Windows Ink Screen Drawing. I don't need it
- [EarTrumpet](https://eartrumpet.app/) for volume adjustment per app. I don't need it
- [Krisp](https://krisp.ai/) for noise cancellation. It's paid
- [GlassBrick](https://www.glassbrickmagnifier.org/) screen magnifier. Use Windows Magnifier instead
- Ditto. Windows Clipboard has history
- ElasticSearch, MongoDB, Redis. Use Docker
- InkScape. It's terrible. Try Figma or something instead
- [Lively Wallpaper](https://rocksdanister.github.io/lively/) for animated wallpapers. Beautiful but too much GPU usage
- [FreeTube](https://freetubeapp.io/) YouTube client. YouTube changes too often for it to keep pace. Prefer piped.video
