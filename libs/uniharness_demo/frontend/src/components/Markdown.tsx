import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeRaw from "rehype-raw";
import CodeBlock from "./CodeBlock";
import MermaidBlock from "./MermaidBlock";
import EChartsBlock from "./EChartsBlock";
import VizBlock from "./VizBlock";
import type { Components } from "react-markdown";

const VIZ_LANGUAGES: Record<string, React.ComponentType<{ children: string; actions?: React.ReactNode }>> = {
  mermaid: MermaidBlock,
  echarts: EChartsBlock,
};

const components: Components = {
  code({ className, children, ...props }) {
    // Inline code only — block code is handled by the pre() component
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  },
  a({ children, href, ...props }) {
    return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
  },
  pre({ children, node }) {
    // Fenced code blocks: extract language from the <code> child's className
    const codeNode = node?.children?.find(
      (c) => c.type === "element" && c.tagName === "code",
    );
    if (codeNode && codeNode.type === "element") {
      const classes = codeNode.properties?.className;
      const langClass = Array.isArray(classes)
        ? classes.find((c) => typeof c === "string" && c.startsWith("language-"))
        : undefined;
      const match = typeof langClass === "string" ? /language-(\w+)/.exec(langClass) : null;

      // Extract raw text from hast children
      const text = codeNode.children
        .map((c) => (c.type === "text" ? c.value : ""))
        .join("")
        .replace(/\n$/, "");

      const lang = match?.[1];
      const Component = lang ? VIZ_LANGUAGES[lang] : undefined;
      if (Component && lang) {
        return <VizBlock language={lang} component={Component}>{text}</VizBlock>;
      }
      return <CodeBlock language={lang}>{text}</CodeBlock>;
    }
    return <pre>{children}</pre>;
  },
};

interface MarkdownProps {
  children: string;
}

export default function Markdown({ children }: MarkdownProps) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} rehypePlugins={[rehypeRaw]} components={components}>
      {children}
    </ReactMarkdown>
  );
}
