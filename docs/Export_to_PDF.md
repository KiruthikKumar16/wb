# Exporting the Report to PDF

Option 1: VS Code extension
- Install "Markdown PDF" by yzane.
- Open `docs/Smart_Jewelry_Safety_Project_Report.md`.
- Right‑click → "Markdown PDF: Export (pdf)".
- Mermaid rendering: install "Markdown Preview Mermaid Support" (or paste images after exporting from mermaid.live).

Option 2: Pandoc
```
pandoc docs/Smart_Jewelry_Safety_Project_Report.md -o Smart_Jewelry_Safety_Project_Report.pdf --pdf-engine=xelatex
```
- To embed Mermaid, pre-render diagrams: open each `.mmd` in https://mermaid.live, export as PNG/SVG, and replace code blocks with images.

Option 3: GitHub/Browser print
- View the Markdown as rendered HTML (e.g., in VS Code Preview or a Markdown viewer).
- Print to PDF (Ctrl+P) with “Background graphics” enabled.

Screenshots
- Before exporting, add screenshots to the report (search “Screenshots” in the report and replace the placeholders).


