# Troubleshooting Upload Errors

## Common Upload Issues

### File Won't Upload / Page Freezes
This usually happens with files larger than 5MB, especially PNG images. Workarounds:
- Compress the image before uploading (we recommend keeping files under 5MB).
- Try a different browser — this issue is most common on Firefox with very large PNGs.
- Clear your browser cache if uploads consistently stall at the same percentage.

### Unsupported File Type
Supported formats are: PNG, JPG, PDF, CSV, and DOCX. Other formats will be rejected with an error message.

### CSV Export Never Completes
If the "Export CSV" button spins indefinitely, this is typically caused by a very large dataset (100k+ rows). Exports over this size are processed in the background and emailed to you instead of downloading directly — check your inbox after a few minutes.

## When to Escalate
If a user reports upload failures on a small, supported file type after trying the above steps, this is likely a genuine bug — escalate to engineering rather than repeating the same troubleshooting steps.
