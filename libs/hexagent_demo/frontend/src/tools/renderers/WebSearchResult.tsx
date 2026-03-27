/**
 * Custom inline renderer for WebSearch tool results.
 *
 * Parses the output to extract search result links and renders them
 * as a list with favicons, titles, and domain names.
 */

import type { ResultRendererProps } from "../types";
import { letterColor } from "../parse";
import { useFavicon } from "../useFavicon";

interface SearchLink {
  title: string;
  url: string;
  domain: string;
}

/** Parse WebSearch output to extract links. */
function parseLinks(output: string): SearchLink[] {
  const linksIdx = output.indexOf("Links: ");
  if (linksIdx === -1) return [];

  const arrayStart = output.indexOf("[", linksIdx);
  if (arrayStart === -1) return [];

  let depth = 0;
  let arrayEnd = -1;
  for (let i = arrayStart; i < output.length; i++) {
    if (output[i] === "[") depth++;
    else if (output[i] === "]") {
      depth--;
      if (depth === 0) { arrayEnd = i; break; }
    }
  }
  if (arrayEnd === -1) return [];

  try {
    const raw = JSON.parse(output.slice(arrayStart, arrayEnd + 1)) as { title?: string; url?: string }[];
    return raw
      .filter((item) => typeof item.title === "string" && typeof item.url === "string")
      .map((item) => {
        let domain = "";
        try {
          domain = new URL(item.url!).hostname;
        } catch {
          // invalid URL
        }
        return { title: item.title!, url: item.url!, domain };
      });
  } catch {
    return [];
  }
}

/** Favicon with cascading fallback via shared useFavicon hook. */
function Favicon({ url, domain }: { url: string; domain: string }) {
  const { src, showFallback } = useFavicon(domain, url);

  if (src) {
    return <img className="websearch-favicon" src={src} alt="" />;
  }

  if (showFallback) {
    const letter = (domain[0] || "?").toUpperCase();
    return (
      <span className="websearch-favicon websearch-favicon-letter" style={{ background: letterColor(domain) }}>
        {letter}
      </span>
    );
  }

  return <span className="websearch-favicon" />;
}

export default function WebSearchResult({ output }: ResultRendererProps) {
  const links = parseLinks(output);
  if (links.length === 0) return null;

  return (
    <div className="websearch-results">
      <div className="websearch-list">
        {links.map((link, i) => (
          <a
            key={i}
            className="websearch-item"
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            title={link.url}
          >
            <Favicon url={link.url} domain={link.domain} />
            <span className="websearch-title">{link.title}</span>
            <span className="websearch-domain">{link.domain}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
