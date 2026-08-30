# FellowQuant Launch Splash Specification

## Source

- Reference: https://typora.io/
- Adapted into: `src/quant_platform/web/welcome.py`
- Interaction model: time-driven typing/deleting loop with an anchor link to the existing welcome content.

## Visual Contract

- Full viewport section using `100svh` and `100vw`.
- Centered `FellowQuant` brand title.
- Secondary monospace line: `/* AI-NATIVE RESEARCH WORKBENCH */`.
- Deep FellowQuant gradient: teal center glow, dark navy edges, subtle ember glow near the lower-left.
- Bottom centered chevron scroll affordance.
- Existing welcome page remains intact after the splash.

## Motion Contract

- The phrase reveals progressively from left to right.
- The phrase remains fully visible briefly, then contracts from right to left to simulate backspace.
- The loop repeats continuously.
- Typora-inspired cadence uses a 6.2 second cycle with a visible cursor blink.
- Reduced-motion users receive the browser's standard reduced-motion behavior through the existing global theme rules.

## Responsive Behavior

- Desktop: title scales up to the official-page hero scale; phrase retains wide tracking.
- Mobile: title scales down, phrase tracking reduces, and the splash remains exactly viewport width with no horizontal overflow.
- The scroll anchor targets `#aq-welcome-start` immediately before the existing hero.

## Continuation Header Behavior

- The topbar is hidden while the launch splash is in view.
- A lightweight parent-page scroll listener toggles `html.aq-welcome-passed` after the splash bottom has crossed the viewport.
- The topbar fades/slides into view when the original welcome hero begins.
- Scrolling back into the splash removes the class and hides the topbar again.
- A fixed, pointer-transparent canvas particle layer replaces continuous background zoom/drift. Particles collapse toward the pointer and softly spring back, with reduced-motion support.
