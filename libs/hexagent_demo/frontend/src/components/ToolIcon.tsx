import { getToolIcon } from "../tools";

export { getToolIcon };

interface ToolIconProps {
  name: string;
  className?: string;
}

export default function ToolIcon({ name, className }: ToolIconProps) {
  const Icon = getToolIcon(name);
  return <Icon className={className} />;
}
