/**
 * Sidebar renderer for TodoWrite tool results.
 *
 * Displays the todo list as a progress checklist with status indicators,
 * or a placeholder message when no tasks are tracked yet.
 */

import { Check, Loader } from "lucide-react";
import { useTranslation } from "../../i18n";

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
  active_form?: string;
}

interface TodoProgressProps {
  todos: TodoItem[] | null;
}

export default function TodoProgress({ todos }: TodoProgressProps) {
  const { t } = useTranslation();
  return (
    <div className="todo-progress">
      {todos ? (
        todos.map((todo, i) => (
          <div className={`todo-item todo-${todo.status}`} key={i}>
            <div className={`todo-icon todo-icon-${todo.status}`}>
              {todo.status === "completed" && <Check size={12} />}
              {todo.status === "in_progress" && <Loader size={12} />}
              {todo.status === "pending" && (
                <span className="todo-order">{i + 1}</span>
              )}
            </div>
            <span className="todo-label">
              {todo.status === "in_progress" && todo.active_form
                ? todo.active_form
                : todo.content}
            </span>
          </div>
        ))
      ) : (
        <p className="todo-empty">{t("todoProgress.empty")}</p>
      )}
    </div>
  );
}

/**
 * Extract todo items from a TodoWrite tool call's input.
 * Returns null if the input doesn't match the expected shape.
 */
export function extractTodos(input: Record<string, unknown>): TodoItem[] | null {
  if (!Array.isArray(input.todos)) return null;
  const items: TodoItem[] = [];
  for (const item of input.todos) {
    if (
      typeof item === "object" && item !== null &&
      typeof item.content === "string" &&
      typeof item.status === "string" &&
      (item.status === "pending" || item.status === "in_progress" || item.status === "completed")
    ) {
      items.push({
        content: item.content,
        status: item.status,
        active_form: typeof item.active_form === "string" ? item.active_form : undefined,
      });
    }
  }
  return items.length > 0 ? items : null;
}
