# Vox Animation

Build a Vox-style cut-paper explainer video with no camera.

One continuous generated world, a character that accumulates through it, type set inside the frame
rather than under it, and an animation whose timing comes from a real voiceover instead of a guess.

Built for a 29 second reel that runs ten beats at 2.9 seconds each.

## What you need

| Step | Tool | Cost |
|---|---|---|
| Generate the scenes | Higgsfield (`seedance_2_5`) | paid, ~45 credits per 1080p scene. **Swappable** for any image-to-video model that takes a start frame |
| Voice | Fish Audio (`s2.1-pro-free`) | **free** |
| HTML to video | Puppeteer, or HyperFrames | free / your plan |
| Conform and mux | ffmpeg | free |

```bash
npm i puppeteer
npm i -g ffmpeg-static
npx hyperframes      # optional
```

Higgsfield and Fish Audio are third-party accounts, not installs.

## The rule that makes it work

**Anchor every scene to the same frame.** Never chain scene two onto scene one, then three onto two.
Chained in a line, each generation inherits the last one's small errors and by scene six you have a
different character in the same colours.

Full method in [SKILL.md](SKILL.md).

## Licence

MIT
