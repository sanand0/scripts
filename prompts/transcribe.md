# transcribe

## Create transcribe script, 22 Oct 2026

<!-- Create transcribe script: https://chatgpt.com/c/6ad99da6-15d0-83ec-9060-8f4cc1ad801f (2026-10-22T14:26:59+08:00) -->

On [LocalMCP2](/plugins/plugin_asdk_app_6ab0b6c561508191882e58b23665db3e) at ~/code/scripts I'd like to create a transcribe script (uv, bash, whatever) that transcribes one or more files specified on the CLI. By default, I'd like it to behave like call, but FAR simpler. The default --prompt should just be "Transcribe". No audio splitting, no patching, no list changes, nothing. I should be able to say transcribe file1.mp3 /path/to/file2.opus ... --prompt "Transcribe correcting basic spelling and grammar" and it should create .md files in the same directory with the transcript. If the target file exists, skip unless --force is specified. Allow specifying --model and default to the same model as call. Use the same API key mechanism. Keep it simple. Add tests. Run and test.

<!-- Standardize Sync Scripts: https://chatgpt.com/c/6ad99c89-9710-83ec-b465-13ab4b288d71 (2026-10-22T14:27:09+08:00) -->

$ cd ~/code/tds-network-games/.private/audio/tds-human-exchange
$ ~/code/scripts/transcribe 0b901d38-6754-4142-956f-ed61d19dc3b8.webm
ERROR 0b901d38-6754-4142-956f-ed61d19dc3b8.webm: 400 FAILED_PRECONDITION. {'error': {'code': 400, 'message': 'The File twy8vulg0gfz is not in an ACTIVE state and usage is not allowed.', 'status': 'FAILED_PRECONDITION'}}

---

OK. Switch the default model to gemini-3.8-flash. If there's levels of thinking we can configure, use the lowest.

---

Change the `call` script as well to default to gemini-3.8-flash with `low`.

---

If a transcript fails, skip and CONTINUE.

---

For these files in ~/code/tds-network-games/.private/audio/tds-human-exchange, "Gemini returned an empty transcript":

FAILED 17/365 recording(s): 5b0a6c21-1540-43b4-9d63-bc898fa0781c.webm, 5ce122e6-7bed-400f-9fd4-d2668ad226de.webm, 6eacf810-27c9-4e26-a87e-cb117ab2270a.webm, 87c749a1-61ab-4fa3-8cfd-0d012ec51ac3.webm, 152e2518-6235-48a4-875a-8a229d92e55a.webm, 222b3d81-0b3a-4261-b671-975f4fb70341.webm, 10993b5f-2581-42d9-9ba3-607355acac1e.webm, 843910cd-522e-4fa1-8752-239b11d53926.webm, 892943f0-80c3-4dbc-8ed4-e89b53132e24.webm, 93767627-2303-4b5b-bd01-259aab907751.webm, a76f5fad-e6fa-471e-914d-67b96cb82635.webm, aa9291ae-4a0a-4f0a-8362-6b75550b9b95.webm, b3fc2eaa-f290-4034-a751-bda6f30af9f2.webm, c7033229-3c08-48ca-bed5-f5395a42223a.webm, f983f2a6-b3bd-4dfb-b9ad-61122783a5a1.webm, f4368226-b2b1-4282-87fa-6ae27f0fc4ad.webm, fb86714d-dd5c-466d-b530-0761477f1af0.webm

Why? I was able to listen to the audio (at least for the first few when I tested) and they DID have speech.

Also, I'd like each row to print the cost of the transcription and the model used.
