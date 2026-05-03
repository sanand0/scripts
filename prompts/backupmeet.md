# Backup Meet

<!--

cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/Meet\ Recordings/:/home/sanand/Documents/Meet\ Recordings/ \
  -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/ \
  -v /home/sanand/.config/gws-root.node@gmail.com/:/home/sanand/.config/gws-root.node@gmail.com/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium

-->

## Generate script, 01 May 2026

Write a script `backupmeet` that uses `gws` CLI and connects to my Google Drive as root.node@gmail.com, copies my Google Meet meeting recordings and transcripts (older than 1 week by default) into `/home/sanand/Documents/Meet Recordings/`, and deletes them.

I might be logged into gws as s.anand@gramener.com also - make sure this applies only to root.node@gmail.com.

Allow command line filtering by file name, file type, date range - making sure that it's easy to specify `n` days ago from today.
Make this an agent-friendly CLI to the extent possible. I'd prefer this to be just a simple shell script, and therefore you may simplify assumptions, leverage `date` for date processing, etc.
Test by actually archiving videos older than a year (or 6 months - or any time period that doesn't have too large a video set to copy.)

Ensure that also

1. Renames them to begin with the meeting date, e.g. `2026-04-30 Innovation Team Meeting.*`
2. Converts the videos (.mp4) into .opus using: `ffmpeg -hide_banner -stats -v warning -i $file -c:a libopus -b:a 12k -ac 1 -application voip -vbr on -compression_level 10 (string replace -r '\.[^.]+$' '.opus' $file)` ensuring that the .opus is saved at `/home/sanand/Documents/calls/`

Update README.md.

---

Would this have been more compact in Python?

---

Rewrite in Python as well.

---

I logged in as root.node@gmail.com and --dry-run works fine. But I get this error. Fix it.

❯ backupmeet.py
Using keyring backend: keyring
account: root.node@gmail.com
query: trashed=false and (name contains 'Recording' or name contains 'Transcript' or name contains 'Notes by Gemini') and createdTime < '2026-04-25T00:00:00Z'
Using keyring backend: keyring
Archive and permanently delete 115 Drive files from root.node@gmail.com? Type yes: yes
Using keyring backend: keyring
error[api]: Only files with binary content can be downloaded. Use Export with Docs Editors files.
Traceback (most recent call last):
  File "/home/sanand/code/scripts/backupmeet.py", line 296, in <module>
    main()
  File "/home/sanand/code/scripts/backupmeet.py", line 283, in main
    download(file, tmp, args.config_dir)
  File "/home/sanand/code/scripts/backupmeet.py", line 180, in download
    gws(args, config_dir, output)
  File "/home/sanand/code/scripts/backupmeet.py", line 64, in gws
    return run(["gws", *args], config_dir, output)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/sanand/code/scripts/backupmeet.py", line 58, in run
    subprocess.run(cmd, check=True, env=env, stdout=out)
  File "/usr/lib/python3.12/subprocess.py", line 571, in run
    raise CalledProcessError(retcode, process.args,
subprocess.CalledProcessError: Command '['gws', 'drive', 'files', 'get', '--params', '{"fileId":"1AJPqXfUWRT-UjtNkBcRPQsMpt8be_aYi","alt":"media"}']' returned non-zero exit status 1.

---

Try now

---

Delete backupmeet and just focus on backupmeet.py.
Now, I get an error saying I don't have delete permissions. If that's the case, it should mention what file path to delete (manually) and proceed to the next file.
If a file has already been downloaded fully, and is not modified on the server, skip it.

❯ backupmeet.py
Using keyring backend: keyring
account: root.node@gmail.com
query: trashed=false and mimeType != 'application/vnd.google-apps.folder' and (name contains 'Recording' or name contains 'Transcript' or name contains 'Notes by Gemini') and createdTime < '2026-04-25T00:00:00Z'
Using keyring backend: keyring
Archive and permanently delete 111 Drive files from root.node@gmail.com? Type yes: yes
Using keyring backend: keyring
Using keyring backend: keyring
error[api]: The user does not have sufficient permissions for this file.
Traceback (most recent call last):
  File "/home/sanand/code/scripts/backupmeet.py", line 307, in <module>
    main()
  File "/home/sanand/code/scripts/backupmeet.py", line 300, in main
    gws(["drive", "files", "delete", "--params", j({"fileId": file["id"]})], args.config_dir)
  File "/home/sanand/code/scripts/backupmeet.py", line 66, in gws
    return run(["gws", *args], config_dir, output)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/sanand/code/scripts/backupmeet.py", line 62, in run
    return subprocess.run(cmd, check=True, env=env, stdout=subprocess.PIPE, text=True).stdout
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/subprocess.py", line 571, in run
    raise CalledProcessError(retcode, process.args,
subprocess.CalledProcessError: Command '['gws', 'drive', 'files', 'delete', '--params', '{"fileId":"19vmyT0NcrXKv2Wy2EhCf1csWfqJs285qYZOEpLzXnew"}']' returned non-zero exit status 1.

---

How can we make this file simpler, shorter, more maintainable?

---

Proceed with your preferred refactor.

<!-- codex resume 019de87c-7d39-7790-b256-a1c702966e0d --yolo -->
