---
title: pdfcpu
source: https://github.com/copilot/c/dd9dcb4e-45fd-4aff-b2fb-98143b583a24
---

```bash
# 1. Split PDF pages into n equal parts symmetrically
pdfcpu ndown -pages 1-10 -- "n:2" input.pdf output_dir

# 2. Create poster by cutting pages into tiles for large format printing
pdfcpu poster -- "formsize:A4, papersize:A3" input.pdf output_dir

# 3. Arrange multiple pages or images into grid layout for browsing
pdfcpu grid -- "rows:3, cols:3" input.pdf output.pdf

# 4. Extract and list all form fields with their IDs
pdfcpu form list input.pdf

# 5. Fill PDF forms from JSON or CSV data
pdfcpu form fill input.pdf data.json output.pdf

# 6. Lock specific form fields to make them read-only
pdfcpu form lock input.pdf output.pdf fieldID1 fieldID2

# 7. Export PDF form structure and data to JSON
pdfcpu form export input.pdf output.json

# 8. Create PDF with forms and content from JSON declaration
pdfcpu create input.json output.pdf

# 9. Import and convert multiple images to single PDF
pdfcpu import image1.jpg image2.png output.pdf

# 10. Add or remove bookmarks (table of contents) via JSON
pdfcpu bookmarks import input.pdf bookmarks.json output.pdf

# 11. Collect and reorder pages into custom sequence
pdfcpu collect input.pdf output.pdf "1,3,2,5-10,4"

# 12. Cut pages horizontally or vertically with custom positioning
pdfcpu cut -- "hor:0.5, vert:0.3" input.pdf output_dir

# 13. Update or replace embedded images by object number or ID
pdfcpu images update input.pdf newimage.jpg output.pdf objNum:123

# 14. Set document page layout mode for PDF viewer behavior
pdfcpu pagelayout set input.pdf output.pdf TwoPageLeft

# 15. Set viewer preferences for how PDF opens and displays
pdfcpu viewerpref set input.pdf preferences.json output.pdf

# 16. Add or remove document properties and custom metadata
pdfcpu properties add input.pdf output.pdf "Author:John Doe" "Custom:Value"

# 17. List and manage PDF portfolio/attachments with descriptions
pdfcpu portfolio add input.pdf output.pdf file1.pdf file2.doc

# 18. Resize pages to specific dimensions or paper formats
pdfcpu resize -- "form:A4, enforce:true" input.pdf output.pdf

# 19. Zoom in or out on selected pages with custom factors
pdfcpu zoom -- "pages:1-5, factor:1.5" input.pdf output.pdf

# 20. Install custom TrueType fonts for embedding in PDFs
pdfcpu fonts install customfont.ttf
```
