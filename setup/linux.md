❯ systemctl --user start org.gnome.SettingsDaemon.MediaKeys.target


❯ systemctl --user status org.gnome.SettingsDaemon.MediaKeys.service

● org.gnome.SettingsDaemon.MediaKeys.service - GNOME keyboard shortcuts service
     Loaded: loaded (/usr/lib/systemd/user/org.gnome.SettingsDaemon.MediaKeys.service; static)
     Active: active (running) since Tue 2025-11-18 14:57:40 +08; 5s ago
   Main PID: 52453 (gsd-media-keys)
      Tasks: 6 (limit: 76201)
     Memory: 3.7M (peak: 4.9M)
        CPU: 29ms
     CGroup: /user.slice/user-1000.slice/user@1000.service/session.slice/org.gnome.SettingsDaemon.MediaKeys.service
             └─52453 /usr/libexec/gsd-media-keys

Nov 18 14:57:40 graphene systemd[15163]: Starting org.gnome.SettingsDaemon.MediaKeys.service - GNOME keyboard shortcuts service...
Nov 18 14:57:40 graphene systemd[15163]: Started org.gnome.SettingsDaemon.MediaKeys.service - GNOME keyboard shortcuts service.
Nov 18 14:57:40 graphene gsd-media-keys[52453]: Failed to grab accelerator for keybinding settings:rotate-video-lock
