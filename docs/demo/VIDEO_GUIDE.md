# MatchForge Demo Video — Editing Guide

**Target**: ~55s main video for X Developer EXhibit + supporting GIFs/clips for listing and launch thread.

## Script Beats (from EXHIBIT_SUBMISSION.md)

1. Drag screenshot → trust badges (≈10s)
2. **@handle verification + live agent trace panel** (hero, ≈20s) ← Lead with this
3. Report + X Social Proof score + claims + citations (≈10s)
4. "Get verification questions" (≈5s)
5. Share badge → public page + OG card + post-to-X (≈10s)

Lead the video with beat 2 (or put it right after a 3-5s hook).

## Deliverables Needed

- `matchforge-demo-55s.mp4` (main video, 1080p, clean)
- GIFs (looping, 5-12s each):
  - screenshot-upload.gif
  - agent-trace-hero.gif
  - report-claims.gif
  - verification-questions.gif
  - share-badge.gif
- Short clips for LAUNCH_THREAD.md posts 4,5, etc.

## Recommended Editing Pipeline (ffmpeg)

All commands assume you have `ffmpeg` installed.

### Basic trim a clip
```bash
ffmpeg -i raw_clip.mp4 -ss 00:00:03 -to 00:00:18 -c:v libx264 -preset fast -crf 20 -c:a aac trimmed.mp4
```

### Concatenate multiple clips in order (create concat.txt first)
concat.txt:
```
file 'beat2_agent_trace.mp4'
file 'beat3_report.mp4'
file 'beat4_questions.mp4'
```

```bash
ffmpeg -f concat -safe 0 -i concat.txt -c copy matchforge-demo-raw.mp4
```

### Add subtle text overlays (example for hero trace moment)
```bash
ffmpeg -i input.mp4 -vf "drawtext=text='Live Grok agent trace':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=h-80:box=1:boxcolor=black@0.6, drawtext=text='x_search + web_search':fontcolor=#1da1f2:fontsize=18:x=(w-text_w)/2:y=h-50" -c:a copy with_text.mp4
```

### Create high-quality looping GIF from a clip (hero shot)
```bash
# Scale to ~800px wide, 12fps, loop
ffmpeg -i agent_trace.mp4 -vf "fps=12,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" -loop 0 agent-trace-hero.gif
```

### Speed up slow sections (e.g. make a 25s trace feel snappier)
```bash
ffmpeg -i long_trace.mp4 -filter:v "setpts=0.75*PTS" -filter:a "atempo=1.333" faster.mp4
```

### Final compression for EXhibit upload (keep quality)
```bash
ffmpeg -i final.mp4 -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 128k -movflags +faststart matchforge-exhibit-demo.mp4
```

## Tips Specific to This App

- Show the **agent trace details expanded** (click the summary so the list of x_search/web_search queries is visible).
- The trace appears after the POST + page reload in the current flow.
- Use prod (match-forge.com) footage for the strongest demo (full X API + Grok blend).
- Keep mouse movements deliberate and not too fast.
- For the "wow" factor: pause or slow slightly on the populated trace list + citations.
- Dashboard zoom ~110-125% during capture is good.
- Crop tightly to content (remove browser chrome if possible).

## Next Actions

1. Share the list of raw files + rough timestamps of good sections.
2. Decide final order (recommended: short hook or direct into beat 2).
3. I'll give you exact commands for your specific clips.
4. Once assembled, we update:
   - docs/demo/EXHIBIT_SUBMISSION.md (add video link)
   - docs/demo/demo-video.md
   - docs/demo/LAUNCH_THREAD.md (reference the clips/GIFs)

Files go in `docs/demo/assets/`.

Current raw files in workspace: (none yet — transfer your best takes when ready)
