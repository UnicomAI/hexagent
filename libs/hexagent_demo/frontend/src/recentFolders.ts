/** Shared recent-folders persistence (localStorage). */

export interface RecentFolder {
  path: string;
  /** "Always Allow" in the permission dialog → true here. */
  alwaysAllowed: boolean;
}

const STORAGE_KEY = "clawwork_recent_folders";

export function loadRecentFolders(): RecentFolder[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    // Migrate from old string[] format
    if (Array.isArray(parsed) && parsed.length > 0 && typeof parsed[0] === "string") {
      return parsed.map((p: string) => ({ path: p, alwaysAllowed: false }));
    }
    return parsed;
  } catch {
    return [];
  }
}

export function saveRecentFolders(folders: RecentFolder[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(folders.slice(0, 8)));
}

/** Shorten a path for display, keeping the final segments visible.
 *  e.g. "/Users/me/long/path/to/project" → ".../path/to/project" */
export function shortenPath(path: string, maxLen = 35): string {
  if (path.length <= maxLen) return path;
  const sep = path.includes("/") ? "/" : "\\";
  const parts = path.split(sep).filter(Boolean);
  // Always show at least the last segment
  let result = parts[parts.length - 1];
  for (let i = parts.length - 2; i >= 0; i--) {
    const next = parts[i] + sep + result;
    if (next.length + 4 > maxLen) break; // 4 = ".../"
    result = next;
  }
  return result === path ? path : "..." + sep + result;
}
