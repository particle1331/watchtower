# Course card generation

Generated with the built-in `image_gen` tool. Opaque background.

```text
Use case: stylized-concept
Asset type: course card artwork for Watchtower, a course called AI-Assisted Development: A Process That Scales.
Primary request: a playful editorial illustration about a human developer and a friendly small AI coding robot collaboratively assembling a carefully structured software system.
Scene: an uncluttered miniature workshop. The human guides the build from a simple architectural sketch while the robot fits tidy modular blocks into a three-level software structure; a few tiny checkmarks suggest verification.
Style/medium: polished tactile 3D clay illustration, charming and witty, soft matte surfaces, clean forms readable at thumbnail size.
Composition/framing: wide landscape 3:2 image, main human/robot/build centered with generous quiet margins safe for course-card cropping. Keep the scene simple.
Color palette: warm white background, charcoal elements and vivid orange accents matching Watchtower's existing white/charcoal/orange site.
Lighting/mood: soft studio lighting, warm upbeat good fun.
Constraints: no words, no letters, no logos, no watermark, no UI screenshot, opaque background.
```

## Previous framing edit

The first image was used as the edit target. The previous asset was `course-card-v2.png`, generated with the built-in tool using this prompt:

```text
Use case: precise-object-edit
Asset type: horizontal course card artwork. Edit target: the supplied friendly clay illustration of a developer and an AI robot building a software architecture.
Change only composition and framing: retain the same human, same robot, same software blocks, palette, material, and warm white backdrop, but pull the camera back so ALL of their heads and feet and the stack remain visible when the image is center-cropped to a wide card about 2.35:1. Put the complete subjects inside the central 50% of the canvas height with ample plain warm-white breathing room above and below. Prefer a wide 2.35:1 canvas. Keep the central scene large enough to read at a small thumbnail size.
Constraints: do not change the characters or art style, do not add new objects, no words, no logos, no watermark. The finished artwork must remain cheerful and fun.
```

## Tighter card framing

The final selected asset is `course-card-v3.png`. The built-in tool first tightened the previous image with this prompt:

```text
Use case: precise-object-edit
Asset type: course card artwork for a horizontal thumbnail displayed at about 355 by 150 pixels.
Edit target: the supplied clay illustration of a human developer and a friendly AI robot assembling software blocks.
Preserve the same characters, expressions, architectural sketch, blocks, checkmarks, matte clay material, orange/charcoal palette, and warm white background.
Change only the composition and framing: the current version has far too much empty space and the characters look tiny. Create a tight, lively horizontal composition at approximately 2.35:1. Enlarge the human, robot, and block structure substantially so the whole scene fills roughly 85–90% of the width and 90–95% of the height. Keep their heads and the robot antenna completely visible, with only a small margin above them. Position the developer toward the left, blocks in the center, and robot toward the right; their faces and gestures should be immediately readable at thumbnail size. Reduce blank space on every side. Keep the complete main scene in frame with small margins; do not pull the camera back or surround the scene with generous whitespace.
Constraints: retain the cheerful tactile art style; no additional characters, no words, no letters, no logo, no watermark. Opaque background.
```

A second built-in edit of that intermediate result added a small safety margin:

```text
Use case: precise-object-edit
Asset type: wide course card thumbnail, approximately 2.35:1.
Edit target: the supplied tightly framed clay illustration of a developer and AI robot assembling software blocks.
Make one small framing correction: zoom the complete existing scene out by about 12%, centered vertically and horizontally, using the same warm white background to fill the small newly revealed border. The developer's entire hair silhouette must be visible with a clear margin above it, and the bottom of the software structure and all feet must be inside the image with a small margin beneath. Keep the characters large and readable; the scene should still occupy about 85% of the image width and height. Avoid the excessive empty space of a distant camera.
Preserve every character, pose, facial expression, architecture sketch, block, checkmark, material, palette, lighting and art style. Change only framing. No new objects, no words, no logos, no watermark. Opaque background.
```
