# After Effects-style implementation guide

This guide translates observed visual principles into an authoring workflow.
It does not claim the reference creators used After Effects, reveal their
project settings, or provide an AE project that was executed in this workspace.
The preset numbers are starting values to tune, not measured properties of
the reference videos.

## Scene graph and timing

Create a 1080×1920, square-pixel, 30 fps main composition. Build separate
foreground, subject and background planes. Place the explanatory world above
the bottom UI area, with critical artwork inside x=60–900, y=220–1180.
Keep the background oversized enough to cover the full frame during motion.

Use 12 fps precomps for intrinsic cutout poses and preserve their timing when
nested. Wrap them in 30 fps world-placement layers. Camera, mattes, kinetic
type and captions remain at 30 fps. Keep captions as 2D screen-space layers;
camera moves should not make them wobble, blur or leave the safe area.

Start with a modest depth budget: three separated planes are usually enough.
Excessive z separation or depth of field can make thin paper look like a toy
stage. Maintain a consistent perspective, horizon, light direction and shadow.

## Speed Graph, not one default easing

Adobe documents that the Speed Graph controls the rate of change, with handle
influence controlling how quickly the curve reaches the keyframe value.
Default Easy Ease is zero speed with 33.33% influence on either side; that is
a convenience preset, not an art-direction decision.

For each event, define a brief anticipation if needed, travel, deceleration
and a readable hold. Use a strong ease-out for an evidence push; use a balanced
curve for a comparison/matte reveal. Avoid repeated camera bounce. Temporal
Bezier controls in the JSON recipes describe value-vs-time; spatial paths
must be designed separately. CSS cubic-Bezier values are not AE influence
percentages and must not be pasted into the wrong control.

## Camera and anchor control

Adobe camera layers can view 3D layers from different angles/distances and
support pans, dolly moves and depth of field. Ordinary 2D HUD layers do not
receive that camera perspective.

Use a camera/parent-null rig and one named intention per shot. A small push
should reveal a detail, a track should follow the causal object, and a turn
should expose a hidden surface. Do not add motion solely to keep the frame
busy. Use matched screen anchors across an object-carry cut.

When labels refer to 3D objects, project their anchor points into screen space
and keep readable type in the 2D overlay. Recheck the full path against the
safe zone, not just the first and last keyframes.

## Mattes and physical reveals

A track matte supplies another layer's visibility from an alpha or luminance
channel. A moving matte can expose an interior, a source passage or a
comparison. Check the chosen normal/inverted mode rather than guessing it.

For a paper cross-section, separate the surface, interior and attached labels.
Move or remove the surface while the interior stays spatially registered.
Then animate the causal action inside it. A full-screen paper wipe between
two static cards is a transition, not a cross-section demonstration.

## Motion blur and finish

Enable the appropriate layer and composition motion-blur switches. Start at
180° shutter angle / -90° phase, which centers the exposure interval, then
tune by normal-speed playback. Use actual transform/shutter sampling for fast
movement; an overall Gaussian blur cannot reproduce directional motion blur.

Keep paper pose changes deliberately crisp when that supports the craft
style. Let camera/world motion remain fluid. Preview nested timing and blur
together; reduce softening if the paper cadence disappears. Keep captions and
critical reading type sharp.

Use subtle contact shadows and restrained focus. Grain should look like
material, not compression noise. Inspect native-resolution alpha edges on
both light and dark backgrounds. The paper phone's old soft surrounding haze
is an example of what the new asset gate should catch before a future edit.

## A practical rage-bait redesign

1. Start inside a paper phone/post world with an immediate absurd image.
2. Carry the same post into a macro correction/reply action.
3. Follow the reply thread into an occlusion reveal of the attention incentive.
4. Compare the visible argument with the intended reaction without fabricating
   guaranteed algorithmic reach or revenue.
5. Show an exit/feedback choice inside the same world.
6. Return the phone, cursor and post to their registered opening positions.

This is a redesign plan, not a claim that the already-delivered rage-bait MP4
has been re-rendered. The old film remains the v1 production artifact.

## Backend equivalence

For a local compositor, require an explicit scene graph, temporal Bezier
curves, camera projection/parallax, alpha masks/occlusion, and temporal shutter
sampling. Render type at native size after camera-world compositing. Test
transformed bounds and overscan on all frames. If those features are absent,
extend the renderer before declaring the result premium.

Native AE project files should be included only when actually authored and
opened in AE. Another renderer can produce an After Effects-style result, but
its source should be named and delivered honestly.

## Official technical references

- Speed Graph and Easy Ease:
  https://helpx.adobe.com/after-effects/desktop/animate-in-after-effects/speed-between-keyframes/speed.html
- Motion blur, shutter angle and phase:
  https://helpx.adobe.com/after-effects/desktop/animate-in-after-effects/assorted-animation-tools/assorted-animation-tools.html
- Cameras and points of interest:
  https://helpx.adobe.com/after-effects/desktop/work-with-layers/camera-layer/cameras-lights-points-interest.html
- Track mattes:
  https://helpx.adobe.com/after-effects/desktop/work-with-transparency-and-compositing/work-with-track-mattes-and-traveling-mattes/track-mattes-and-traveling-mattes.html
