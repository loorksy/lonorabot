const wrapper = /^<peer_outcome\b[^>]*status=['"]([^'"]+)['"][^>]*>\n([\s\S]*)\n<\/peer_outcome>$/;

/**
 * A colleague's result reaches the conversation inside a machine wrapper (run id and
 * status) that agents read; the owner sees only the result. A text without the wrapper
 * comes back unchanged.
 */
export function peerOutcome(content: string): { body: string; status?: string } {
  const match = wrapper.exec(content);
  return match ? { body: match[2], status: match[1] } : { body: content };
}
