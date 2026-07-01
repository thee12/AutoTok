# TikTok Review Demo Video Guide

Use this as a short recording plan for the TikTok Developer app review demo. A 1-3 minute MP4 is enough if it clearly shows the complete integration flow.

## Recommended Recording

1. Open a terminal in `C:\Users\danie\Projects\AutoTok`.
2. Activate the virtual environment and run `autotok doctor`.
3. Show the local workflow creating or inspecting a render package.
4. Start the review dashboard with `autotok review serve`.
5. Open the local dashboard and show the rendered video review screen.
6. Approve the render package in the dashboard.
7. Return to the terminal and show a TikTok publishing dry run:

   ```powershell
   autotok publish tiktok RENDER_ID --source file_upload --privacy-level SELF_ONLY --json
   ```

8. Explain that real publishing requires the same approved render plus explicit `--execute --confirm`.

## Suggested Narration

InTheLoop is a local-first workflow powered by AutoTok. It creates short-form video packages from approved source text and authorized media. I review the generated video locally before anything can be published. Login Kit is used to authorize my TikTok account, and Content Posting API is used for file-upload Direct Post with the `video.publish` scope. The app does not automate likes, comments, messages, follows, or other engagement behavior. Publishing requires human review and explicit confirmation.

## TikTok Review Explanation

You can paste this into the app review explanation field:

```text
InTheLoop is a local-first desktop workflow powered by AutoTok. It helps me create short-form videos from approved source text and authorized media, review the rendered video locally, and publish approved videos to my own TikTok account through TikTok's official Content Posting API. Login Kit is used to authorize my TikTok account. Content Posting API is used for file-upload Direct Post with the video.publish scope. Publishing requires explicit human review and confirmation before upload. The app does not automate comments, direct messages, follows, likes, or other engagement behavior.
```

## TikTok Form URLs

After GitHub Pages is enabled for the repository, use:

- Platform URL: `https://thee12.github.io/AutoTok/`
- Terms of Service URL: `https://thee12.github.io/AutoTok/terms.html`
- Privacy Policy URL: `https://thee12.github.io/AutoTok/privacy.html`