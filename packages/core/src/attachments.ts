// Matches the Python upload boundary; byte limits are checked again on the server.
export const maxAttachmentBytes = 20 * 1024 * 1024;
export function attachmentTooLarge(size: number | undefined): boolean {
  return size !== undefined && size > maxAttachmentBytes;
}
