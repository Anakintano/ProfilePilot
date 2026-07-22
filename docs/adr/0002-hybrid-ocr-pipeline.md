# ADR 0002: Hybrid PyMuPDF + OpenCV + PaddleOCR pipeline, with graceful degradation

## Status
Accepted

## Context
Uploaded documents are a mix of digitally-generated PDFs (LinkedIn export,
Word/Docs résumé exports) and scanned/photographed screenshots. Most digital
PDFs already contain selectable text — running OCR on those wastes time and
loses precision. Scanned pages have no embedded text and need real OCR.
PaddleOCR is a heavy dependency (paddlepaddle + model downloads) that is
known to be fragile to install/run in constrained or offline environments.

## Decision
Text-first extraction: PyMuPDF (`fitz`) reads embedded text with bounding
boxes wherever present. Only pages/regions with no usable embedded text are
rendered to an image and pushed through OpenCV preprocessing (deskew,
denoise, contrast normalization, downscaling) and then PaddleOCR.

The PaddleOCR call is wrapped so that an import failure, model-download
failure, or a runtime error/timeout does not fail the job — it is treated as
"OCR unavailable for this page," logged as an honest progress event, and
surfaced to the user on the extraction-review screen rather than silently
fabricating content or crashing the pipeline.

A text-based LLM fallback is reserved for section classification only, and
only when the deterministic keyword-header heuristic
(`services/worker/app/extraction/sectionize.py`) still leaves a required
section (contact/experience/education/skills) missing after its pass —
`services/worker/app/extraction/reclassify.py` re-examines blocks the
heuristic tagged `other` against the missing sections, using the same
Groq → OpenRouter → deterministic-fallback provider order as recommendation
generation. It relabels existing text; it never invents or transcribes
new content, which is what keeps this in bounds of the OCR-first design's
anti-fabrication intent even though it's a real LLM call. (This turned out
to be a text-only case in practice, not the vision-LLM-for-scanned-pages
case originally anticipated here — the common failure mode observed was a
resume/LinkedIn export using unexpected header wording, e.g. LinkedIn's own
"Top Skills" instead of "Skills", not an unreadable scanned image.)

## Consequences
- The common case (digital PDF) works reliably with zero OCR dependency
  risk.
- The scanned/screenshot case is best-effort in the beta: if PaddleOCR can't
  install or run in a given environment, those pages simply need manual
  correction on the extraction-review screen instead of blocking the whole
  product.
- Every extracted field carries its `extraction_method` and `confidence` so
  the difference between "read directly" and "OCR'd" (and how much to trust
  it) is visible, not hidden.