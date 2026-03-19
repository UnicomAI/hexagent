import { oneLight, oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useThemeMode } from "./useThemeMode";

/**
 * Returns the syntax highlighting theme matching the current document theme.
 *
 * Shared between CodeBlock (chat) and CodeViewer (file preview) so both
 * resolve the theme the same way and only one place needs updating.
 */
export function useSyntaxTheme() {
  const mode = useThemeMode();
  return mode === "dark" ? oneDark : oneLight;
}
