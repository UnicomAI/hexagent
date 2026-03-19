import { useState, useEffect, useRef, useCallback } from "react";
import { Settings2, Unplug, ScrollText, Bot, ChevronRight, Settings } from "lucide-react";
import { useAppContext } from "../store";
import { listSkills, toggleSkill, updateServerConfig, testMcpConnection } from "../api";
import type { SkillsList, AgentConfig, McpServerEntry, ServerConfig } from "../api";

interface InputSettingsMenuProps {
  onOpenSettings: (tab: string) => void;
  /** Open panel downward (welcome page) or upward (conversation page). */
  dropUp?: boolean;
}

type SubmenuKey = "mcp" | "skills" | "agents";

type McpStatus = { state: "validating" } | { state: "ok"; tools: number } | { state: "failed" };

export default function InputSettingsMenu({ onOpenSettings, dropUp = false }: InputSettingsMenuProps) {
  const { state, dispatch } = useAppContext();
  const [open, setOpen] = useState(false);
  const [submenu, setSubmenu] = useState<SubmenuKey | null>(null);
  const [skills, setSkills] = useState<SkillsList | null>(null);
  const [mcpStatus, setMcpStatus] = useState<Record<string, McpStatus>>({});
  const ref = useRef<HTMLDivElement>(null);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout>>(null);

  const close = useCallback(() => {
    setOpen(false);
    setSubmenu(null);
  }, []);

  // Click-outside close
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, close]);

  // Escape key closes
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, close]);

  // Fetch skills when menu opens
  useEffect(() => {
    if (!open) return;
    listSkills().then(setSkills).catch(() => {});
  }, [open]);

  // Reset mcpStatus when menu opens (fresh state each time)
  useEffect(() => {
    if (open) setMcpStatus({});
  }, [open]);

  // Cleanup hover timer
  useEffect(() => () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
  }, []);

  const mcpServers: McpServerEntry[] = state.serverConfig?.mcp_servers ?? [];
  const agents: AgentConfig[] = state.serverConfig?.agents ?? [];

  // MCP toggle with connection validation (consistent with Settings)
  const handleToggleMcp = useCallback(
    async (server: McpServerEntry) => {
      if (!state.serverConfig) return;

      if (server.enabled) {
        // Toggling OFF — immediate
        const updated: ServerConfig = {
          ...state.serverConfig,
          mcp_servers: state.serverConfig.mcp_servers.map((s) =>
            s.id === server.id ? { ...s, enabled: false } : s
          ),
        };
        dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
        updateServerConfig(updated).catch(() => {});
        setMcpStatus((prev) => { const next = { ...prev }; delete next[server.id]; return next; });
        return;
      }

      // Toggling ON — validate first
      setMcpStatus((prev) => ({ ...prev, [server.id]: { state: "validating" } }));

      try {
        const result = await testMcpConnection({
          ...server, enabled: true,
        });

        if (result.ok) {
          // Commit the toggle
          const updated: ServerConfig = {
            ...state.serverConfig!,
            mcp_servers: state.serverConfig!.mcp_servers.map((s) =>
              s.id === server.id ? { ...s, enabled: true } : s
            ),
          };
          dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
          updateServerConfig(updated).catch(() => {});
          setMcpStatus((prev) => ({ ...prev, [server.id]: { state: "ok", tools: result.tools ?? 0 } }));
        } else {
          setMcpStatus((prev) => ({ ...prev, [server.id]: { state: "failed" } }));
        }
      } catch {
        setMcpStatus((prev) => ({ ...prev, [server.id]: { state: "failed" } }));
      }
    },
    [state.serverConfig, dispatch]
  );

  const handleToggleAgent = useCallback(
    (agentId: string) => {
      if (!state.serverConfig) return;
      const updated: ServerConfig = {
        ...state.serverConfig,
        agents: (state.serverConfig.agents ?? []).map((a) =>
          a.id === agentId ? { ...a, enabled: !a.enabled } : a
        ),
      };
      dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
      updateServerConfig(updated).catch(() => {});
    },
    [state.serverConfig, dispatch]
  );

  const handleToggleSkill = useCallback(
    (name: string, currentlyDisabled: boolean) => {
      const nowEnabled = currentlyDisabled;
      setSkills((prev) => {
        if (!prev) return prev;
        const disabled = new Set(prev.disabled);
        if (nowEnabled) disabled.delete(name);
        else disabled.add(name);
        return { ...prev, disabled: Array.from(disabled) };
      });
      toggleSkill(name, nowEnabled).catch(() => {
        listSkills().then(setSkills).catch(() => {});
      });
    },
    []
  );

  const handleManage = useCallback(
    (tab: string) => {
      close();
      onOpenSettings(tab);
    },
    [onOpenSettings, close]
  );

  // Debounced hover to avoid flickering between parent items
  const scheduleSubmenu = useCallback((target: SubmenuKey) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => setSubmenu(target), 80);
  }, []);

  const cancelSchedule = useCallback(() => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
  }, []);

  const allSkills = skills
    ? [
        ...skills.public.map((name) => ({ name, disabled: skills.disabled.includes(name) })),
        ...skills.user.map((name) => ({ name, disabled: skills.disabled.includes(name) })),
      ]
    : [];

  const dirCls = dropUp ? "ism--up" : "ism--down";

  // Render a submenu panel
  const renderSubmenu = (items: React.ReactNode, manageTab: string, manageLabel: string) => (
    <div className={`dd-panel ism-submenu ${dirCls}`} onMouseEnter={cancelSchedule}>
      <div className="ism-submenu-scroll">
        {items}
      </div>
      <div className="dd-divider" />
      <button className="dd-item ism-manage-item" onClick={() => handleManage(manageTab)}>
        <Settings size={14} className="ism-item-icon" />
        <span className="dd-item-label">{manageLabel}</span>
      </button>
    </div>
  );

  // MCP status dot: always present for alignment, color reflects state
  const mcpStatusDot = (server: McpServerEntry) => {
    const status = mcpStatus[server.id];
    let cls = "ism-status-dot";
    if (status?.state === "validating") cls += " ism-status-dot--validating";
    else if (status?.state === "failed") cls += " ism-status-dot--failed";
    else if (status?.state === "ok" || server.enabled) cls += " ism-status-dot--on";
    return <span className={cls} />;
  };

  // Determine the switch class for MCP (accounts for validating/failed states)
  const mcpSwitchClass = (server: McpServerEntry) => {
    const status = mcpStatus[server.id];
    if (status?.state === "validating") return "ism-switch ism-switch--validating";
    if (status?.state === "failed") return "ism-switch ism-switch--failed";
    if (server.enabled) return "ism-switch ism-switch--on";
    return "ism-switch";
  };

  return (
    <div className={`ism ${dirCls}`} ref={ref}>
      <button
        className="input-tool-btn"
        title="Settings"
        onClick={() => { if (open) close(); else setOpen(true); }}
      >
        <Settings2 />
      </button>

      {open && (
        <div className={`dd-panel ism-panel ${dirCls}`}>
          {/* MCP */}
          <button
            className={`dd-item ism-parent-item ${submenu === "mcp" ? "ism-parent-item--active" : ""}`}
            onMouseEnter={() => scheduleSubmenu("mcp")}
            onClick={() => setSubmenu(submenu === "mcp" ? null : "mcp")}
          >
            <Unplug size={16} className="ism-item-icon" />
            <span className="dd-item-label">MCP</span>
            <ChevronRight size={14} className="ism-chevron" />
          </button>

          {/* Skills */}
          <button
            className={`dd-item ism-parent-item ${submenu === "skills" ? "ism-parent-item--active" : ""}`}
            onMouseEnter={() => scheduleSubmenu("skills")}
            onClick={() => setSubmenu(submenu === "skills" ? null : "skills")}
          >
            <ScrollText size={16} className="ism-item-icon" />
            <span className="dd-item-label">Skills</span>
            <ChevronRight size={14} className="ism-chevron" />
          </button>

          {/* Subagent */}
          <button
            className={`dd-item ism-parent-item ${submenu === "agents" ? "ism-parent-item--active" : ""}`}
            onMouseEnter={() => scheduleSubmenu("agents")}
            onClick={() => setSubmenu(submenu === "agents" ? null : "agents")}
          >
            <Bot size={16} className="ism-item-icon" />
            <span className="dd-item-label">Subagent</span>
            <ChevronRight size={14} className="ism-chevron" />
          </button>

          {/* Subagent submenu */}
          {submenu === "agents" &&
            renderSubmenu(
              agents.length === 0 ? (
                <div className="ism-empty">No subagents configured</div>
              ) : (
                agents.map((agent) => (
                  <button
                    key={agent.id}
                    className="dd-item ism-toggle-item"
                    onClick={() => handleToggleAgent(agent.id)}
                  >
                    <span className="dd-item-label">{agent.name || "Untitled"}</span>
                    <span className={`ism-switch ${agent.enabled ? "ism-switch--on" : ""}`} />
                  </button>
                ))
              ),
              "agents",
              "Manage Subagents..."
            )}

          {/* MCP submenu */}
          {submenu === "mcp" &&
            renderSubmenu(
              mcpServers.length === 0 ? (
                <div className="ism-empty">No MCP servers configured</div>
              ) : (
                mcpServers.map((server) => (
                  <button
                    key={server.id}
                    className="dd-item ism-toggle-item"
                    disabled={mcpStatus[server.id]?.state === "validating"}
                    onClick={() => handleToggleMcp(server)}
                  >
                    {mcpStatusDot(server)}
                    <span className="dd-item-label">{server.name || "Untitled"}</span>
                    <span className={mcpSwitchClass(server)} />
                  </button>
                ))
              ),
              "mcps",
              "Manage MCP Servers..."
            )}

          {/* Skills submenu */}
          {submenu === "skills" &&
            renderSubmenu(
              allSkills.length === 0 ? (
                <div className="ism-empty">No skills installed</div>
              ) : (
                allSkills.map(({ name, disabled }) => (
                  <button
                    key={name}
                    className="dd-item ism-toggle-item"
                    onClick={() => handleToggleSkill(name, disabled)}
                  >
                    <span className="dd-item-label">{name}</span>
                    <span className={`ism-switch ${!disabled ? "ism-switch--on" : ""}`} />
                  </button>
                ))
              ),
              "skills",
              "Manage Skills..."
            )}
        </div>
      )}
    </div>
  );
}
