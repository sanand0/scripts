---
title: pdfcpu
docs: https://github.com/pdfcpu/pdfcpu
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

# 21. Add text or image stamps that appear on top of page content
pdfcpu stamp add -- "mode:text, text:CONFIDENTIAL, rot:45, opacity:0.5" input.pdf output.pdf

# 22. Add watermarks that appear behind page content with positioning
pdfcpu watermark add -- "mode:image, file:logo.png, pos:tl, offset:10 10" input.pdf output.pdf

# 23. Update existing stamps or watermarks on selected pages
pdfcpu stamp update -pages 1-10 -- "mode:text, text:REVISED" input.pdf output.pdf

# 24. Remove all stamps from specific pages
pdfcpu stamp remove -pages 1-5 -- input.pdf output.pdf

# 25. Encrypt PDF with password and set user/owner passwords separately
pdfcpu encrypt -upw userpass -opw ownerpass input.pdf output.pdf

# 26. Decrypt password-protected PDF to remove encryption
pdfcpu decrypt -upw password input.pdf output.pdf

# 27. Set granular user access permissions (print, copy, modify, etc)
pdfcpu permissions set -perm none+print+copy input.pdf output.pdf

# 28. List all user permissions on encrypted PDFs
pdfcpu permissions list input.pdf

# 29. Rotate pages by specific degrees (90, 180, 270)
pdfcpu rotate -pages 1-10 -- 90 input.pdf output.pdf

# 30. Split PDF into multiple files by page span or bookmarks
pdfcpu split -mode span input.pdf output_dir 5

# 31. Split PDF at specific page numbers into separate files
pdfcpu split -mode page input.pdf output_dir 3 7 12

# 32. Extract embedded fonts from PDF for analysis or reuse
pdfcpu extract -mode font input.pdf output_dir

# 33. Extract text content from all pages to separate files
pdfcpu extract -mode content input.pdf output_dir

# 34. Extract metadata (XMP, document info) to separate file
pdfcpu extract -mode metadata input.pdf output_dir

# 35. Optimize PDF by removing redundant objects and compressing
pdfcpu optimize input.pdf output.pdf

# 36. Validate PDF against PDF 1.7 standard and report issues
pdfcpu validate -mode relaxed input.pdf

# 37. List and add page annotations (comments, highlights, notes)
pdfcpu annotations list -pages 1-10 input.pdf

# 38. Remove specific annotations by ID or type from pages
pdfcpu annotations remove input.pdf output.pdf objNr:123

# 39. Arrange pages into booklet format for physical printing
pdfcpu booklet -- "formsize:A4" input.pdf output.pdf

# 40. Validate digital signatures and certificates in signed PDFs
pdfcpu signatures validate input.pdf
```
