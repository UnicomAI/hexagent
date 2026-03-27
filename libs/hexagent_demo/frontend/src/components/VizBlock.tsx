import { useState } from "react";
import { Code2, Eye } from "lucide-react";
import CodeBlock from "./CodeBlock";

interface VizBlockProps {
  language: string;
  children: string;
  component: React.ComponentType<{ children: string; actions?: React.ReactNode }>;
}

/**
 * Wraps a visualization component (Mermaid/ECharts) with a source-code toggle.
 * Default: rendered visualization.  Click the Code button to see source.
 */
export default function VizBlock({ language, children, component: Component }: VizBlockProps) {
  const [showSource, setShowSource] = useState(false);

  if (showSource) {
    return (
      <CodeBlock
        language={language}
        extraActions={
          <button
            className="code-block-action-btn"
            onClick={() => setShowSource(false)}
            title="View rendered"
          >
            <Eye />
          </button>
        }
      >
        {children}
      </CodeBlock>
    );
  }

  return (
    <Component
      actions={
        <button
          className="viz-action-btn"
          onClick={() => setShowSource(true)}
          title="View source"
        >
          <Code2 />
        </button>
      }
    >
      {children}
    </Component>
  );
}
