/**
 * Utilities for extracting values from incomplete/streaming JSON.
 *
 * During tool call streaming, argsText is an incomplete JSON string like:
 *   {"description": "List files in
 * We need to extract field values before the JSON is complete.
 */

/**
 * Extract a string field value from possibly-incomplete JSON.
 *
 * Handles:
 * - Complete values: {"field": "value", ...} → "value"
 * - Incomplete values: {"field": "partial val → "partial val"
 * - JSON escape sequences: \", \\, \n, \t, \uXXXX
 * - Field not yet present: {"ot → undefined
 *
 * @returns The (possibly partial) string value, or undefined if field not found.
 */
export function extractPartialField(argsText: string, field: string): string | undefined {
  // Search for "field" :
  const key = `"${field}"`;
  const keyIdx = argsText.indexOf(key);
  if (keyIdx === -1) return undefined;

  let i = keyIdx + key.length;

  // Skip whitespace
  while (i < argsText.length && isWhitespace(argsText[i])) i++;

  // Expect ':'
  if (i >= argsText.length || argsText[i] !== ":") return undefined;
  i++;

  // Skip whitespace
  while (i < argsText.length && isWhitespace(argsText[i])) i++;

  // Expect opening '"'
  if (i >= argsText.length || argsText[i] !== '"') return undefined;
  i++;

  // Extract string content, handling escape sequences
  let value = "";
  while (i < argsText.length) {
    const ch = argsText[i];
    if (ch === "\\") {
      if (i + 1 >= argsText.length) break; // incomplete escape at end
      const next = argsText[i + 1];
      switch (next) {
        case '"':  value += '"';  i += 2; break;
        case "\\": value += "\\"; i += 2; break;
        case "/":  value += "/";  i += 2; break;
        case "n":  value += "\n"; i += 2; break;
        case "t":  value += "\t"; i += 2; break;
        case "r":  value += "\r"; i += 2; break;
        case "b":  value += "\b"; i += 2; break;
        case "f":  value += "\f"; i += 2; break;
        case "u":
          // \uXXXX — need 4 hex digits
          if (i + 5 < argsText.length) {
            const hex = argsText.slice(i + 2, i + 6);
            value += String.fromCharCode(parseInt(hex, 16));
            i += 6;
          } else {
            // Incomplete unicode escape — stop here
            return value || undefined;
          }
          break;
        default:
          // Unknown escape, take literally
          value += next;
          i += 2;
          break;
      }
    } else if (ch === '"') {
      // End of string value
      break;
    } else {
      value += ch;
      i++;
    }
  }

  return value || undefined;
}

function isWhitespace(ch: string): boolean {
  return ch === " " || ch === "\t" || ch === "\n" || ch === "\r";
}

/**
 * Count completed string elements in a JSON array field from incomplete JSON.
 *
 * During streaming, argsText may look like:
 *   {"filepaths": ["/path/one", "/path/two", "/path/thr
 * This returns the number of fully-quoted strings seen (2 in the example).
 *
 * @returns The count of complete string elements, or undefined if the field/array not found.
 */
export function countPartialArrayItems(argsText: string, field: string): number | undefined {
  const key = `"${field}"`;
  const keyIdx = argsText.indexOf(key);
  if (keyIdx === -1) return undefined;

  let i = keyIdx + key.length;

  // Skip whitespace
  while (i < argsText.length && isWhitespace(argsText[i])) i++;

  // Expect ':'
  if (i >= argsText.length || argsText[i] !== ":") return undefined;
  i++;

  // Skip whitespace
  while (i < argsText.length && isWhitespace(argsText[i])) i++;

  // Expect '['
  if (i >= argsText.length || argsText[i] !== "[") return undefined;
  i++;

  // Count complete quoted strings
  let count = 0;
  while (i < argsText.length) {
    const ch = argsText[i];
    if (isWhitespace(ch) || ch === ",") { i++; continue; }
    if (ch === "]") break;
    if (ch !== '"') { i++; continue; }

    // Walk through the string, handling escapes
    i++; // skip opening quote
    let closed = false;
    while (i < argsText.length) {
      if (argsText[i] === "\\") { i += 2; continue; }
      if (argsText[i] === '"') { closed = true; i++; break; }
      i++;
    }
    if (closed) count++;
  }

  return count;
}

/** Deterministic color from a string (e.g. domain). */
export function letterColor(s: string): string {
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    hash = s.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = ((hash % 360) + 360) % 360;
  return `hsl(${hue}, 45%, 55%)`;
}
