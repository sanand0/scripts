#!/usr/bin/bash

# Toggle GNOME extension to restart it after screen blank
# https://claude.ai/chat/9f993bc0-ba50-46e0-b0d5-38a77c0b8621

/usr/bin/gsettings set org.gnome.shell disable-user-extensions true
/usr/bin/gsettings set org.gnome.shell disable-user-extensions false
sleep 0.2
/usr/bin/gnome-extensions disable ubuntu-appindicators@ubuntu.com
/usr/bin/gnome-extensions enable ubuntu-appindicators@ubuntu.com
