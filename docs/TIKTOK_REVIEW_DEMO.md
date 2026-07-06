# TikTok Manual Upload Demo Guide

Use this as a short recording plan if you want to show the current AutoTok
publishing workflow. This is no longer a TikTok Developer app review demo
because AutoTok does not use TikTok APIs for publishing.

## Recommended Recording

1. Open a terminal in `C:\Users\danie\Projects\AutoTok`.
2. Activate the virtual environment and run `autotok doctor`.
3. Show or create a completed render package.
4. Start the review dashboard with `autotok review serve`.
5. Open the local dashboard and show the rendered video review screen.
6. Approve the render package in the dashboard.
7. Return to the terminal and prepare a manual TikTok package:

   ```powershell
   autotok publish tiktok RENDER_ID --json
   ```

8. Open the generated `manual_upload` folder and show `video.mp4`,
   `caption.txt`, `metadata.json`, and `instructions.md`.
9. Explain that you upload the video yourself in TikTok and click the final
   publish button manually.
10. Optionally show local status recording:

   ```powershell
   autotok publish mark RENDER_ID --url https://www.tiktok.com/@you/video/123
   ```

## Suggested Narration

InTheLoop is a local-first workflow powered by AutoTok. It creates short-form
TikTok video packages from approved source text and authorized media. I review
the generated video locally, then AutoTok prepares a folder with the rendered
MP4, caption, metadata, and manual upload instructions. AutoTok does not connect
to TikTok Login Kit, request TikTok scopes, upload through TikTok APIs, or click
publish for me. I manually upload and publish from my own TikTok account after
reviewing TikTok's own prompts and settings.

## Website URLs

If GitHub Pages is enabled for the repository, use:

- Platform URL: `https://thee12.github.io/AutoTok/`
- Terms of Service URL: `https://thee12.github.io/AutoTok/terms.html`
- Privacy Policy URL: `https://thee12.github.io/AutoTok/privacy.html`
