# Publishing (optional, open-ended)

Making the video is this skill's job. Posting it is optional, and how is left to you. The suggested route is **Buffer**, which schedules to Instagram, TikTok, YouTube Shorts and others from one API.

## Suggested approach
1. Ask the user if they want it published, and where (Instagram Reels, TikTok, YouTube Shorts ...), plus caption/hashtags and when (now, scheduled, or save as draft).
2. Ask for a **Buffer API access token** (from their Buffer account's developer/API settings). Buffer's API and access rules change, so read the current docs at https://developers.buffer.com (or search for them) instead of relying on memory. If Buffer API access is not available to the account, say so and offer alternatives (the platform's own API, or the user uploads by hand).
3. Keep the token out of the repo, config in this skill, chat logs and command lines you print: use an environment variable (e.g. `BUFFER_ACCESS_TOKEN`) or the OS credential store. Never commit it.
4. Buffer needs a public URL or an upload for the media; follow the current docs for whichever it supports. Upload the final captioned MP4 from `output_dir`.
5. Prefer creating a **draft or scheduled post** and show the user what will go out (channel, text, time, video) before it is published, unless they told you to post straight away.
6. Report back what was created (post id/link, channel, status) and anything that failed. Do not retry a failed publish blindly: check the queue first so nothing is posted twice.

Write whatever small script you need for this yourself (Python `urllib`/`requests`, or curl). If you build something reusable, tell the user so it can be added to the skill.
