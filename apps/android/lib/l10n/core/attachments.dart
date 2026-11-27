/// Port of packages/core/src/attachments.ts: the upload size limit (checked again on the
/// server). An attachment over it shows the `attachment_too_large` label.
library;

/// Matches the Python upload boundary (attachments.ts:1-2).
const int maxAttachmentBytes = 20 * 1024 * 1024;

/// Whether a file is over [maxAttachmentBytes] (attachments.ts:3-5).
bool attachmentTooLarge(int? size) => size != null && size > maxAttachmentBytes;
