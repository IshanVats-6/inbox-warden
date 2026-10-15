# Mailhub

All UI must follow DESIGN.md.

- DESIGN.md (Notion design system, from VoltAgent/awesome-design-md, MIT) is the source of truth for colours, type, spacing, radii, shadows and components.
- Use the tokens in `mailhub/static/style.css`; don't hard-code new colours or sizes in templates.
- Purple (`--primary`) is for the one main action on a page. Links use `--link`. Buttons are 8px rectangles, cards 12px, pills only for filters and status.
- Check new screens in light and dark mode and at phone width. Run the demo with `DEMO_MODE=true` to see the UI without any credentials.
