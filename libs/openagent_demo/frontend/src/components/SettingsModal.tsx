import { useState, useCallback, useEffect, useRef, createContext, useContext } from "react";
import { X, Plus, Trash2, Monitor, Moon, Sun, Unplug, SlidersHorizontal, Cpu, ChevronDown, ChevronRight, Check, Loader2, Eye, EyeOff, GripVertical, Bot, Wrench, Globe, ScrollText, Zap, FolderOpen, FolderPlus, Server, CircleCheck, CircleAlert, Upload, Package, Download, TriangleAlert } from "lucide-react";
import type { Settings } from "../hooks/useSettings";
import { getServerConfig, updateServerConfig, testMcpConnection, browseFolder, listSkills, uploadSkill, deleteSkill, toggleSkill, installSkill } from "../api";
import { useAppContext } from "../store";
import type { ServerConfig, ModelConfig, AgentConfig } from "../api";
import { loadRecentFolders, saveRecentFolders, shortenPath } from "../recentFolders";
import type { RecentFolder } from "../recentFolders";

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  settings: Settings;
  onSettingsChange: (settings: Settings | ((prev: Settings) => Settings)) => void;
  initialTab?: Tab;
}

export type Tab = "general" | "model" | "mcps" | "tools" | "agents" | "sandbox" | "skills";

const isMac = navigator.platform.toUpperCase().includes("MAC");

/** Tabs call this to report dirty state and expose their save function. */
const SettingsDirtyContext = createContext<{
  reportDirty: (dirty: boolean) => void;
  registerSave: (fn: (() => Promise<void>) | null) => void;
}>({ reportDirty: () => {}, registerSave: () => {} });

function useSettingsDirty(isDirty: boolean, saveFn: () => Promise<void>) {
  const { reportDirty, registerSave } = useContext(SettingsDirtyContext);
  useEffect(() => { reportDirty(isDirty); }, [isDirty, reportDirty]);
  useEffect(() => { registerSave(saveFn); return () => registerSave(null); }, [saveFn, registerSave]);
}

export default function SettingsModal({ open, onClose, settings, onSettingsChange, initialTab }: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab ?? "general");

  // Sync activeTab when initialTab changes while opening
  useEffect(() => {
    if (open && initialTab) setActiveTab(initialTab);
  }, [open, initialTab]);
  const [dirty, setDirty] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const saveRef = useRef<(() => Promise<void>) | null>(null);

  const reportDirty = useCallback((d: boolean) => setDirty(d), []);
  const registerSave = useCallback((fn: (() => Promise<void>) | null) => { saveRef.current = fn; }, []);

  // Reset dirty state when switching tabs
  useEffect(() => { setDirty(false); saveRef.current = null; }, [activeTab]);

  const handleClose = useCallback(() => {
    if (dirty) {
      setShowConfirm(true);
    } else {
      onClose();
    }
  }, [dirty, onClose]);

  const handleDiscard = useCallback(() => {
    setShowConfirm(false);
    setDirty(false);
    onClose();
  }, [onClose]);

  const handleSaveAndClose = useCallback(async () => {
    if (saveRef.current) {
      await saveRef.current();
    }
    setShowConfirm(false);
    setDirty(false);
    onClose();
  }, [onClose]);

  // Exit animation state: "open" | "closing"
  const [animState, setAnimState] = useState<"open" | "closing">("open");

  // Reset animation state when opened
  useEffect(() => {
    if (open) setAnimState("open");
  }, [open]);

  const triggerClose = useCallback(() => {
    if (dirty) {
      setShowConfirm(true);
    } else {
      setAnimState("closing");
    }
  }, [dirty]);

  // Override handleClose to use animated close
  const animatedClose = triggerClose;

  // When discard/save-and-close, also animate
  const animatedDiscard = useCallback(() => {
    setShowConfirm(false);
    setDirty(false);
    setAnimState("closing");
  }, []);

  const animatedSaveAndClose = useCallback(async () => {
    if (saveRef.current) {
      await saveRef.current();
    }
    setShowConfirm(false);
    setDirty(false);
    setAnimState("closing");
  }, []);

  const handleExitDone = useCallback(() => {
    setAnimState("open");
    onClose();
  }, [onClose]);

  // Keyboard: Cmd+Shift+, to close, Escape to close
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const mod = isMac ? e.metaKey : e.ctrlKey;
      if (mod && e.shiftKey && (e.key === "," || e.key === "<" || e.code === "Comma")) {
        e.preventDefault();
        animatedClose();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        animatedClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, animatedClose]);

  if (!open) return null;

  const isClosing = animState === "closing";

  return (
    <SettingsDirtyContext.Provider value={{ reportDirty, registerSave }}>
    <div
      className={`settings-overlay ${isClosing ? "settings-overlay-exit" : ""}`}
      onClick={animatedClose}
      onAnimationEnd={isClosing ? handleExitDone : undefined}
    >
      <div className={`settings-modal ${isClosing ? "settings-modal-exit" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="settings-sidebar">
          <div className="settings-sidebar-header">
            <button className="settings-close" onClick={animatedClose}>
              <X />
            </button>
          </div>
          <button
            className={`settings-tab ${activeTab === "general" ? "active" : ""}`}
            onClick={() => setActiveTab("general")}
          >
            <SlidersHorizontal className="settings-tab-icon" />
            General
          </button>
          <button
            className={`settings-tab ${activeTab === "sandbox" ? "active" : ""}`}
            onClick={() => setActiveTab("sandbox")}
          >
            <Monitor className="settings-tab-icon" />
            Sandbox
          </button>
          <button
            className={`settings-tab ${activeTab === "model" ? "active" : ""}`}
            onClick={() => setActiveTab("model")}
          >
            <Cpu className="settings-tab-icon" />
            Model
          </button>
          <button
            className={`settings-tab ${activeTab === "tools" ? "active" : ""}`}
            onClick={() => setActiveTab("tools")}
          >
            <Wrench className="settings-tab-icon" />
            Tool
          </button>
          <button
            className={`settings-tab ${activeTab === "mcps" ? "active" : ""}`}
            onClick={() => setActiveTab("mcps")}
          >
            <Unplug className="settings-tab-icon" />
            MCP
          </button>
          <button
            className={`settings-tab ${activeTab === "skills" ? "active" : ""}`}
            onClick={() => setActiveTab("skills")}
          >
            <ScrollText className="settings-tab-icon" />
            Skills
          </button>
          <button
            className={`settings-tab ${activeTab === "agents" ? "active" : ""}`}
            onClick={() => setActiveTab("agents")}
          >
            <Bot className="settings-tab-icon" />
            Subagent
          </button>
        </div>

        <div className="settings-content">
          <div className="settings-content-body">
            <h2 className="settings-content-title">
              {{ general: "General", model: "Model", tools: "Tool", mcps: "MCP", agents: "Subagent", sandbox: "Sandbox", skills: "Skills" }[activeTab]}
            </h2>

            {activeTab === "general" && (
              <GeneralTab settings={settings} onChange={onSettingsChange} />
            )}
            {activeTab === "model" && <ModelTab />}
            {activeTab === "mcps" && <McpTab />}
            {activeTab === "tools" && <ToolsTab />}
            {activeTab === "agents" && <SubagentTab />}
            {activeTab === "sandbox" && <SandboxTab />}
            {activeTab === "skills" && <SkillsTab />}
          </div>
        </div>

        {showConfirm && (
          <div className="settings-confirm-overlay" onClick={() => setShowConfirm(false)}>
            <div className="settings-confirm-dialog" onClick={(e) => e.stopPropagation()}>
              <h3 className="settings-confirm-title">Unsaved changes</h3>
              <p className="settings-confirm-body">
                You have unsaved changes that will be lost if you close now.
              </p>
              <div className="settings-confirm-actions">
                <button className="settings-confirm-btn" onClick={() => setShowConfirm(false)}>
                  Cancel
                </button>
                <button className="settings-confirm-btn settings-confirm-btn--discard" onClick={animatedDiscard}>
                  Discard
                </button>
                <button className="settings-confirm-btn settings-confirm-btn--save" onClick={animatedSaveAndClose}>
                  Save & Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
    </SettingsDirtyContext.Provider>
  );
}

function GeneralTab({
  settings,
  onChange,
}: {
  settings: Settings;
  onChange: (s: Settings | ((prev: Settings) => Settings)) => void;
}) {
  return (
    <div className="settings-rows">
      <div className="settings-row">
        <div className="settings-row-label">Full Name</div>
        <div className="settings-row-value">
          <input
            className="settings-input"
            type="text"
            value={settings.fullName}
            onChange={(e) => onChange((prev) => ({ ...prev, fullName: e.target.value }))}
            placeholder="Your name"
          />
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-label">Appearance</div>
        <div className="settings-row-value">
          <div className="settings-theme-options">
            {(["light", "dark", "system"] as const).map((theme) => (
              <button
                key={theme}
                className={`settings-theme-btn ${settings.theme === theme ? "active" : ""}`}
                onClick={() => onChange((prev) => ({ ...prev, theme }))}
              >
                {theme === "light" && <Sun className="settings-theme-icon" />}
                {theme === "dark" && <Moon className="settings-theme-icon" />}
                {theme === "system" && <Monitor className="settings-theme-icon" />}
                <span>{theme.charAt(0).toUpperCase() + theme.slice(1)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Provider Presets ──

interface ProviderPreset {
  id: string;
  label: string;
  base_url: string;
  provider: string;
  custom_url: boolean;
}

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "openai",
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    provider: "openai",
    custom_url: false,
  },
  {
    id: "anthropic",
    label: "Anthropic",
    base_url: "https://api.anthropic.com",
    provider: "anthropic",
    custom_url: false,
  },
  {
    id: "openai-compatible",
    label: "OpenAI-Compatible",
    base_url: "",
    provider: "deepseek",
    custom_url: true,
  },
];

function presetIdFromProvider(provider: string): string {
  const match = PROVIDER_PRESETS.find((p) => p.provider === provider);
  return match ? match.id : "openai-compatible";
}

// ── Model Tab (compact accordion) ──

function ModelTab() {
  const { dispatch } = useAppContext();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showAddPicker, setShowAddPicker] = useState(false);
  const [showKey, setShowKey] = useState<Record<string, boolean>>({});
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<{ idx: number; half: "top" | "bottom" } | null>(null);
  const rowRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const dragFromHandle = useRef(false);

  useEffect(() => {
    getServerConfig().then(setConfig).catch((e: Error) => setError(e.message));
  }, []);

  const markDirty = () => { setDirty(true); setSaved(false); };

  const updateModel = (id: string, updates: Partial<ModelConfig>) => {
    if (!config) return;
    setConfig({
      ...config,
      models: config.models.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    });
    markDirty();
  };

  const addModelWithPreset = (presetId: string) => {
    if (!config) return;
    const preset = PROVIDER_PRESETS.find((p) => p.id === presetId) || PROVIDER_PRESETS[0];
    const newModel: ModelConfig = {
      id: crypto.randomUUID(),
      display_name: "",
      api_key: "",
      base_url: preset.base_url,
      model: "",
      provider: preset.provider,
      context_window: 200000,
      supported_modalities: ["text"],
    };
    const nextConfig = { ...config, models: [...config.models, newModel] };
    if (!nextConfig.main_model_id) {
      nextConfig.main_model_id = newModel.id;
    }
    setConfig(nextConfig);
    setShowAddPicker(false);
    setExpandedId(newModel.id);
    markDirty();
  };

  const deleteModel = (id: string) => {
    if (!config) return;
    const next = { ...config, models: config.models.filter((m) => m.id !== id) };
    if (next.main_model_id === id) next.main_model_id = next.models[0]?.id ?? "";
    if (next.fast_model_id === id) next.fast_model_id = "";
    setConfig(next);
    setConfirmingDeleteId(null);
    if (expandedId === id) setExpandedId(null);
    markDirty();
  };

  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect();
    const half = e.clientY < rect.top + rect.height / 2 ? "top" : "bottom";
    setDropTarget({ idx, half });
  };

  const handleDragEnd = () => {
    if (!config || dragIdx === null || !dropTarget) {
      setDragIdx(null);
      setDropTarget(null);
      return;
    }
    let toIdx = dropTarget.half === "bottom" ? dropTarget.idx + 1 : dropTarget.idx;
    // Adjust for removal offset
    if (dragIdx < toIdx) toIdx--;
    if (dragIdx === toIdx) {
      setDragIdx(null);
      setDropTarget(null);
      return;
    }
    const models = [...config.models];
    const [moved] = models.splice(dragIdx, 1);
    models.splice(toIdx, 0, moved);
    setConfig({ ...config, models });
    setDragIdx(null);
    setDropTarget(null);
    markDirty();
  };

  const handleSave = useCallback(async () => {
    if (!config) return;
    const toSave = { ...config, main_model_id: config.models[0]?.id ?? "" };
    setSaving(true);
    setError("");
    try {
      const updated = await updateServerConfig(toSave);
      setConfig(updated);
      dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
      setSaved(true);
      setDirty(false);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  }, [config, dispatch]);

  useSettingsDirty(dirty, handleSave);

  if (!config) return <div className="settings-section"><p className="settings-hint">Loading configuration...</p></div>;

  return (
    <div className="settings-section">
      <p className="settings-hint">
        Add your AI models below. The first model is the default. Drag to reorder.
      </p>

      {error && <div className="model-error">{error}</div>}

      {/* ── Compact Model List ── */}
      <div className="ml-list">
        {config.models.map((m, idx) => {
          const presetId = presetIdFromProvider(m.provider);
          const preset = PROVIDER_PRESETS.find((p) => p.id === presetId)!;
          const expanded = expandedId === m.id;
          const isKeyVisible = showKey[m.id] ?? false;
          const isDefault = idx === 0;

          return (
            <div
              key={m.id}
              className={`ml-item ${expanded ? "ml-item--expanded" : ""} ${dropTarget?.idx === idx && dropTarget.half === "top" ? "ml-item--drag-top" : ""} ${dropTarget?.idx === idx && dropTarget.half === "bottom" ? "ml-item--drag-bottom" : ""}`}
              draggable
              onDragStart={(e) => {
                if (!dragFromHandle.current) {
                  e.preventDefault();
                  return;
                }
                dragFromHandle.current = false;
                e.dataTransfer.effectAllowed = "move";
                setDragIdx(idx);
                const row = rowRefs.current.get(idx);
                if (row) e.dataTransfer.setDragImage(row, 0, row.offsetHeight / 2);
              }}
              onDragOver={(e) => handleDragOver(e, idx)}
              onDragEnd={handleDragEnd}
            >
              {/* Row header */}
              <div className="ml-row" ref={(el) => { if (el) rowRefs.current.set(idx, el); }} onClick={() => setExpandedId(expanded ? null : m.id)} onMouseDown={() => { dragFromHandle.current = true; }}>
                <div className="ml-drag-handle">
                  <GripVertical size={14} />
                </div>
                <div className="ml-row-info">
                  <div className="ml-row-top">
                    <span className="ml-row-name">{m.display_name || m.model || "Untitled"}</span>
                    {isDefault && <span className="ml-default-badge">Default</span>}
                  </div>
                  <div className="ml-row-meta">
                    {preset.label}{m.model ? ` · ${m.model}` : ""}
                  </div>
                </div>
                <div className="ml-row-actions">
                  {config.models.length > 1 && (
                    <button
                      className="settings-del"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirmingDeleteId === m.id) {
                          deleteModel(m.id);
                        } else {
                          setConfirmingDeleteId(m.id);
                        }
                      }}
                      title={confirmingDeleteId === m.id ? "Click again to confirm" : "Delete"}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                  {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </div>
              </div>

              {confirmingDeleteId === m.id && !expanded && (
                <div className="ml-confirm-bar">
                  <span>Delete this model?</span>
                  <button className="mc-confirm-yes" onClick={() => deleteModel(m.id)}>Delete</button>
                  <button className="mc-confirm-no" onClick={() => setConfirmingDeleteId(null)}>Cancel</button>
                </div>
              )}

              {/* Expanded edit form */}
              <div className={`ml-edit-wrap ${expanded ? "ml-edit-wrap--open" : ""}`}>
                <div className="ml-edit">
                <div className="ml-edit-inner">
                  {/* Provider pills */}
                  <div className="mc-field">
                    <label className="mc-label">Provider</label>
                    <div className="mc-pills">
                      {PROVIDER_PRESETS.map((p) => (
                        <button
                          key={p.id}
                          className={`mc-pill ${presetId === p.id ? "mc-pill--active" : ""}`}
                          onClick={() => {
                            const updates: Partial<ModelConfig> = { provider: p.provider };
                            updates.base_url = p.custom_url ? "" : p.base_url;
                            updateModel(m.id, updates);
                          }}
                          type="button"
                        >
                          {p.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mc-row">
                    <div className="mc-field" style={{ flex: 1 }}>
                      <label className="mc-label">Display Name</label>
                      <input
                        className="mc-input"
                        value={m.display_name}
                        onChange={(e) => updateModel(m.id, { display_name: e.target.value })}
                        placeholder="e.g. My GPT-4"
                      />
                    </div>
                    <div className="mc-field" style={{ flex: 1 }}>
                      <label className="mc-label">Model ID</label>
                      <input
                        className="mc-input"
                        value={m.model}
                        onChange={(e) => updateModel(m.id, { model: e.target.value })}
                        placeholder="e.g. gpt-4.1"
                      />
                    </div>
                  </div>

                  <div className="mc-field">
                    <label className="mc-label">API Key</label>
                    <div className="mc-key-wrap">
                      <input
                        className="mc-input mc-input--key"
                        type={isKeyVisible ? "text" : "password"}
                        value={m.api_key}
                        onChange={(e) => updateModel(m.id, { api_key: e.target.value })}
                        placeholder="sk-..."
                      />
                      <button
                        className="mc-key-toggle"
                        onClick={() => setShowKey((prev) => ({ ...prev, [m.id]: !isKeyVisible }))}
                        title={isKeyVisible ? "Hide" : "Show"}
                        type="button"
                      >
                        {isKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* Base URL */}
                  <div className="mc-field">
                    <label className="mc-label">Base URL</label>
                    <input
                      className="mc-input"
                      value={m.base_url}
                      onChange={(e) => updateModel(m.id, { base_url: e.target.value })}
                      placeholder={preset.custom_url ? "https://api.example.com/v1" : preset.base_url}
                    />
                  </div>

                  {/* Context Window & Modalities — visually separated */}
                  <div className="mc-separator" />
                  <div className="mc-row">
                    <div className="mc-field" style={{ maxWidth: 200 }}>
                      <label className="mc-label">Context Window</label>
                      <input
                        className="mc-input"
                        value={m.context_window || ""}
                        onChange={(e) => updateModel(m.id, { context_window: parseInt(e.target.value.replace(/\D/g, "")) || 0 })}
                        placeholder="200000"
                      />
                    </div>
                    <div className="mc-field" style={{ flex: 1 }}>
                      <label className="mc-label">Input Modalities</label>
                      <div className="mc-pills">
                        <span className="mc-pill mc-pill--active mc-pill--locked">Text</span>
                        {(["image", "audio", "video", "pdf"] as const).map((mod) => {
                          const modalities = m.supported_modalities ?? ["text"];
                          const active = modalities.includes(mod);
                          return (
                            <button
                              key={mod}
                              type="button"
                              className={`mc-pill ${active ? "mc-pill--active" : ""}`}
                              onClick={() => {
                                const next = active
                                  ? modalities.filter((x) => x !== mod)
                                  : [...modalities, mod];
                                updateModel(m.id, { supported_modalities: next });
                              }}
                            >
                              {mod.charAt(0).toUpperCase() + mod.slice(1)}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Add Model ── */}
      {showAddPicker ? (
        <div className="add-picker">
          <div className="add-picker-label">Choose a provider:</div>
          <div className="add-picker-grid">
            {PROVIDER_PRESETS.map((p) => (
              <button key={p.id} className="add-picker-btn" onClick={() => addModelWithPreset(p.id)}>
                {p.label}
              </button>
            ))}
          </div>
          <button className="add-picker-cancel" onClick={() => setShowAddPicker(false)}>Cancel</button>
        </div>
      ) : (
        <div className="model-actions">
          <button className="model-add-btn" onClick={() => setShowAddPicker(true)}>
            <Plus size={16} /> Add Model
          </button>
        </div>
      )}

      {/* ── Summarizer Model ── */}
      {config.models.length > 0 && (
        <div className="tools-summarizer">
          <div className="tools-summarizer-left">
            <Zap size={13} className="tools-summarizer-icon" />
            <span className="tools-summarizer-title">Summarizer Model</span>
            <span className="tools-summarizer-desc">fast model for web page summarization</span>
          </div>
          <div className="tools-summarizer-right">
            <CustomSelect
              value={config.fast_model_id}
              options={[
                { value: "", label: "Default" },
                ...config.models.map((m) => ({ value: m.id, label: m.display_name })),
              ]}
              onChange={(v) => { setConfig({ ...config, fast_model_id: v }); markDirty(); }}
            />
          </div>
        </div>
      )}

      {/* ── Save ── */}
      <div className="model-save-bar">
        {dirty && !saved && <span className="model-unsaved-hint">Unsaved changes</span>}
        <button
          className={`model-save-btn ${saved ? "saved" : ""}`}
          onClick={handleSave}
          disabled={saving || (!dirty && !saved)}
        >
          {saving ? (
            <><Loader2 size={14} className="model-save-spinner" /> Applying...</>
          ) : saved ? (
            <><Check size={14} /> Saved</>
          ) : dirty ? (
            "Save & Apply"
          ) : (
            "No Changes"
          )}
        </button>
      </div>
    </div>
  );
}

// ── Key-Value Pair Editor ──
// Stores data as JSON string but presents a friendly key/value row UI.

interface KVPair { key: string; value: string }

function jsonToKVPairs(json: string): KVPair[] {
  try {
    const obj = JSON.parse(json);
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      const entries = Object.entries(obj).map(([k, v]) => ({ key: k, value: String(v) }));
      return entries.length > 0 ? entries : [{ key: "", value: "" }];
    }
  } catch { /* ignore */ }
  return [{ key: "", value: "" }];
}

function kvPairsToJson(pairs: KVPair[]): string {
  const obj: Record<string, string> = {};
  for (const { key, value } of pairs) {
    const k = key.trim();
    if (k) obj[k] = value;
  }
  return Object.keys(obj).length > 0 ? JSON.stringify(obj) : "";
}

function KeyValueEditor({
  label,
  value,
  onChange,
  keyPlaceholder = "KEY",
  valuePlaceholder = "value",
  secretValues = false,
}: {
  label: string;
  value: string;
  onChange: (val: string) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  secretValues?: boolean;
}) {
  const [pairs, setPairs] = useState<KVPair[]>(() => jsonToKVPairs(value));
  const valueRef = useRef(value);
  const [visibleIdx, setVisibleIdx] = useState<Set<number>>(new Set());

  // Sync from parent only when the external value actually changes
  useEffect(() => {
    if (value !== valueRef.current) {
      valueRef.current = value;
      setPairs(jsonToKVPairs(value));
    }
  }, [value]);

  const commit = (next: KVPair[]) => {
    setPairs(next);
    const json = kvPairsToJson(next);
    valueRef.current = json;
    onChange(json);
  };

  const update = (idx: number, field: "key" | "value", val: string) => {
    commit(pairs.map((p, i) => (i === idx ? { ...p, [field]: val } : p)));
  };

  const addRow = () => {
    setPairs((prev) => {
      if (secretValues) {
        setVisibleIdx((v) => new Set(v).add(prev.length));
      }
      return [...prev, { key: "", value: "" }];
    });
  };

  const removeRow = (idx: number) => {
    const next = pairs.filter((_, i) => i !== idx);
    commit(next.length > 0 ? next : [{ key: "", value: "" }]);
  };

  return (
    <div className="mc-field">
      <label className="mc-label">{label}</label>
      <div className="kv-list">
        {pairs.map((pair, idx) => (
          <div className="kv-row" key={idx}>
            <input
              className="mc-input kv-key"
              value={pair.key}
              onChange={(e) => update(idx, "key", e.target.value)}
              placeholder={keyPlaceholder}
            />
            <div className="kv-value-wrap">
              <input
                className={`mc-input kv-value ${secretValues && !visibleIdx.has(idx) ? "kv-value--masked" : ""}`}
                type="text"
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                data-form-type="other"
                value={pair.value}
                onChange={(e) => update(idx, "value", e.target.value)}
                onBlur={() => { if (secretValues && pair.value) setVisibleIdx((prev) => { const next = new Set(prev); next.delete(idx); return next; }); }}
                placeholder={valuePlaceholder}
              />
              {secretValues && (
                <button
                  className="mc-key-toggle"
                  onClick={() => setVisibleIdx((prev) => {
                    const next = new Set(prev);
                    next.has(idx) ? next.delete(idx) : next.add(idx);
                    return next;
                  })}
                  title={visibleIdx.has(idx) ? "Hide" : "Show"}
                  type="button"
                >
                  {visibleIdx.has(idx) ? <Eye size={12} /> : <EyeOff size={12} />}
                </button>
              )}
            </div>
            <button
              className="settings-del kv-remove"
              onClick={() => removeRow(idx)}
              title="Remove"
              type="button"
            >
              <Trash2 size={12} />
            </button>
          </div>
        ))}
        <button className="kv-add" onClick={addRow} type="button">
          <Plus size={12} /> Add
        </button>
      </div>
    </div>
  );
}

interface McpServer {
  id: string;
  name: string;
  type: "http" | "stdio";
  url?: string;
  command?: string;
  args?: string;
  env?: string;
  headers?: string;
  enabled: boolean;
}

function McpTab() {
  const { dispatch } = useAppContext();
  const [servers, setServers] = useState<McpServer[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [showAddPicker, setShowAddPicker] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [testStatus, setTestStatus] = useState<Record<string, { loading?: boolean; ok?: boolean; tools?: number; error?: string }>>({});
  const [validatingIds, setValidatingIds] = useState<Set<string>>(new Set());
  const [failedIds, setFailedIds] = useState<Set<string>>(new Set());
  const configRef = useRef<ServerConfig | null>(null);
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Load MCP servers from backend (single source of truth)
  useEffect(() => {
    getServerConfig().then((cfg) => {
      configRef.current = cfg;
      setServers(
        (cfg.mcp_servers ?? []).map((s) => ({
          id: s.id || crypto.randomUUID(),
          name: s.name,
          type: s.type as "http" | "stdio",
          url: s.url,
          command: s.command,
          args: s.args,
          env: s.env,
          headers: s.headers,
          enabled: s.enabled,
        })),
      );
    });
  }, []);

  const markDirty = useCallback(() => { setDirty(true); }, []);

  // Test a single server connection
  const testServer = useCallback(async (server: McpServer) => {
    setTestStatus((prev) => ({ ...prev, [server.id]: { loading: true } }));
    try {
      const result = await testMcpConnection({
        id: server.id, name: server.name, type: server.type,
        url: server.url ?? "", command: server.command ?? "",
        args: server.args ?? "", env: server.env ?? "",
        headers: server.headers ?? "", enabled: server.enabled,
      });
      setTestStatus((prev) => ({ ...prev, [server.id]: result }));
      return result;
    } catch {
      const fail = { ok: false as const, error: "Request failed" };
      setTestStatus((prev) => ({ ...prev, [server.id]: fail }));
      return fail;
    }
  }, []);

  // Compute a config fingerprint for change detection
  const fingerprint = useCallback((s: McpServer) =>
    `${s.enabled}|${s.type}|${s.url}|${s.command}|${s.args}|${s.env}|${s.headers}`, []);

  // Auto-test: on mount test all enabled servers, on config change debounce re-test
  // Skip servers currently being validated by handleToggle to avoid double-testing
  const prevFingerprints = useRef<Record<string, string>>({});
  useEffect(() => {
    for (const server of servers) {
      const fp = fingerprint(server);

      // Keep fingerprint current for servers being validated or showing failure
      // so the auto-test won't re-trigger or clear their status
      if (validatingIds.has(server.id) || failedIds.has(server.id)) {
        prevFingerprints.current[server.id] = fp;
        continue;
      }
      const prev = prevFingerprints.current[server.id];

      if (!server.enabled) {
        // Clear status for disabled servers
        if (prev !== undefined) {
          setTestStatus((s) => { const next = { ...s }; delete next[server.id]; return next; });
          if (debounceTimers.current[server.id]) clearTimeout(debounceTimers.current[server.id]);
        }
        prevFingerprints.current[server.id] = fp;
        continue;
      }

      if (prev === fp) continue; // No change

      const wasDisabled = prev !== undefined && prev.startsWith("false|");
      prevFingerprints.current[server.id] = fp;

      // Clear any pending debounce
      if (debounceTimers.current[server.id]) clearTimeout(debounceTimers.current[server.id]);

      if (prev === undefined || wasDisabled) {
        // First mount or just enabled — test immediately
        testServer(server);
      } else {
        // Config changed while enabled — debounce 1.5s
        setTestStatus((s) => ({ ...s, [server.id]: { loading: true } }));
        debounceTimers.current[server.id] = setTimeout(() => testServer(server), 1500);
      }
    }

    // Clean up fingerprints for deleted servers
    const currentIds = new Set(servers.map((s) => s.id));
    for (const id of Object.keys(prevFingerprints.current)) {
      if (!currentIds.has(id)) {
        delete prevFingerprints.current[id];
        if (debounceTimers.current[id]) clearTimeout(debounceTimers.current[id]);
      }
    }
  }); // Intentionally no deps — runs on every render to compare fingerprints

  // Cleanup debounce timers on unmount
  useEffect(() => () => {
    for (const t of Object.values(debounceTimers.current)) clearTimeout(t);
  }, []);

  const addServer = useCallback((type: "http" | "stdio") => {
    const newServer: McpServer = {
      id: crypto.randomUUID(),
      name: "",
      type,
      url: "",
      command: "",
      args: "",
      env: "",
      headers: "",
      enabled: false,
    };
    setServers((prev) => [...prev, newServer]);
    setExpandedId(newServer.id);
    setShowAddPicker(false);
    markDirty();
  }, [markDirty]);

  const updateServer = useCallback(
    (id: string, updates: Partial<McpServer>) => {
      const isToggle = "enabled" in updates;
      setServers((prev) =>
        prev.map((s) => {
          if (s.id !== id) return s;
          // Config change (not toggle) → auto-disable so user must re-validate
          const merged = { ...s, ...updates };
          if (!isToggle && s.enabled) merged.enabled = false;
          return merged;
        }),
      );
      // Clear failed state and test status on any change
      setFailedIds((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      if (!isToggle) {
        setTestStatus((prev) => {
          if (!prev[id]) return prev;
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }
      markDirty();
    },
    [markDirty]
  );

  // Toggle handler: validates connection before enabling
  const handleToggle = useCallback(
    async (server: McpServer, wantEnabled: boolean) => {
      if (!wantEnabled) {
        // Toggling OFF — immediate, no validation
        updateServer(server.id, { enabled: false });
        return;
      }

      // Toggling ON — validate first
      setValidatingIds((prev) => new Set(prev).add(server.id));
      setTestStatus((prev) => ({ ...prev, [server.id]: { loading: true } }));

      const result = await testServer({ ...server, enabled: true });

      if (result.ok) {
        // Connection succeeded — commit the toggle but keep validatingIds
        // so the spinner ring persists until the auto-test confirms tools count
        updateServer(server.id, { enabled: true });
      } else {
        // Connection failed — show error until user changes this server's config
        setValidatingIds((prev) => { const next = new Set(prev); next.delete(server.id); return next; });
        setFailedIds((prev) => new Set(prev).add(server.id));
      }
    },
    [testServer, updateServer]
  );

  // Clear validatingIds once the server is enabled and testStatus confirms tools
  useEffect(() => {
    if (validatingIds.size === 0) return;
    setValidatingIds((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const id of prev) {
        const server = servers.find((s) => s.id === id);
        const status = testStatus[id];
        if (server?.enabled && status && !status.loading) {
          next.delete(id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [testStatus, servers, validatingIds]);

  const deleteServer = useCallback(
    (id: string) => {
      setServers((prev) => prev.filter((s) => s.id !== id));
      setConfirmingDeleteId(null);
      if (expandedId === id) setExpandedId(null);
      markDirty();
    },
    [expandedId, markDirty]
  );

  const handleSave = useCallback(async () => {
    const base = configRef.current;
    if (!base) return;
    const toSave = {
      ...base,
      mcp_servers: servers.map((s) => ({
        id: s.id,
        name: s.name,
        type: s.type,
        url: s.url ?? "",
        command: s.command ?? "",
        args: s.args ?? "",
        env: s.env ?? "",
        headers: s.headers ?? "",
        enabled: s.enabled,
      })),
    };
    const updated = await updateServerConfig(toSave);
    configRef.current = updated;
    dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
    setDirty(false);
  }, [servers, dispatch]);

  useSettingsDirty(dirty, handleSave);

  return (
    <div className="settings-section">
      <p className="settings-hint">
        Configure MCP servers that the agent can connect to. Changes take effect on next agent restart.
      </p>

      {/* Server list */}
      <div className="ml-list">
        {servers.map((server) => {
          const expanded = expandedId === server.id;

          return (
            <div key={server.id} className={`ml-item ${expanded ? "ml-item--expanded" : ""}`}>
              {/* Row header */}
              <div className="ml-row" onClick={() => setExpandedId(expanded ? null : server.id)}>
                <div className="ml-row-info">
                  <div className="ml-row-top">
                    <span className="ml-row-name">{server.name || "Untitled server"}</span>
                    <span className="mcp-type-badge">{server.type.toUpperCase()}</span>
                    {validatingIds.has(server.id) ? (
                      <span className="mcp-status-indicator mcp-status-testing">
                        <Loader2 size={11} className="file-preview-spinner" /><span>Connecting…</span>
                      </span>
                    ) : (server.enabled || failedIds.has(server.id)) && testStatus[server.id] ? (
                      <span className={`mcp-status-indicator ${testStatus[server.id].loading ? "mcp-status-testing" : testStatus[server.id].ok ? "mcp-status-ok" : "mcp-status-fail"}`}>
                        {testStatus[server.id].loading ? (
                          <><Loader2 size={11} className="file-preview-spinner" /><span>Connecting…</span></>
                        ) : testStatus[server.id].ok ? (
                          <><CircleCheck size={11} /><span>{testStatus[server.id].tools} tool{testStatus[server.id].tools === 1 ? "" : "s"} available</span></>
                        ) : (
                          <><CircleAlert size={11} /><span>Failed</span></>
                        )}
                      </span>
                    ) : null}
                  </div>
                  <div className="ml-row-meta">
                    {server.type === "http"
                      ? server.url || "No URL configured"
                      : [server.command, server.args].filter(Boolean).join(" ") || "No command configured"}
                  </div>
                </div>
                <div className="ml-row-actions">
                  <label
                    className={`mcp-toggle ${validatingIds.has(server.id) ? "mcp-toggle--validating" : ""} ${failedIds.has(server.id) ? "mcp-toggle--failed" : ""}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={server.enabled || validatingIds.has(server.id)}
                      disabled={validatingIds.has(server.id)}
                      onChange={(e) => handleToggle(server, e.target.checked)}
                    />
                    <span className="mcp-toggle-slider" />
                  </label>
                  <button
                    className="settings-del"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirmingDeleteId === server.id) {
                        deleteServer(server.id);
                      } else {
                        setConfirmingDeleteId(server.id);
                      }
                    }}
                    title={confirmingDeleteId === server.id ? "Click again to confirm" : "Delete"}
                  >
                    <Trash2 size={14} />
                  </button>
                  {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </div>
              </div>

              {confirmingDeleteId === server.id && !expanded && (
                <div className="ml-confirm-bar">
                  <span>Delete this server?</span>
                  <button className="mc-confirm-yes" onClick={() => deleteServer(server.id)}>Delete</button>
                  <button className="mc-confirm-no" onClick={() => setConfirmingDeleteId(null)}>Cancel</button>
                </div>
              )}

              {/* Expanded edit form */}
              <div className={`ml-edit-wrap ${expanded ? "ml-edit-wrap--open" : ""}`}>
                <div className="ml-edit">
                  <div className="ml-edit-inner">
                    {/* Type pills */}
                    <div className="mc-field">
                      <label className="mc-label">Type</label>
                      <div className="mc-pills">
                        <button
                          className={`mc-pill ${server.type === "http" ? "mc-pill--active" : ""}`}
                          onClick={() => updateServer(server.id, { type: "http" })}
                          type="button"
                        >
                          HTTP
                        </button>
                        <button
                          className={`mc-pill ${server.type === "stdio" ? "mc-pill--active" : ""}`}
                          onClick={() => updateServer(server.id, { type: "stdio" })}
                          type="button"
                        >
                          Stdio
                        </button>
                      </div>
                    </div>

                    <div className="mc-field">
                      <label className="mc-label">Name</label>
                      <input
                        className="mc-input"
                        value={server.name}
                        onChange={(e) => updateServer(server.id, { name: e.target.value })}
                        placeholder="e.g. context7"
                      />
                    </div>

                    {server.type === "http" && (
                      <>
                        <div className="mc-field">
                          <label className="mc-label">URL</label>
                          <input
                            className="mc-input"
                            value={server.url ?? ""}
                            onChange={(e) => updateServer(server.id, { url: e.target.value })}
                            placeholder="https://example.com/mcp"
                          />
                        </div>
                        <KeyValueEditor
                          label="Headers"
                          value={server.headers ?? ""}
                          onChange={(val) => updateServer(server.id, { headers: val })}
                          keyPlaceholder="Header-Name"
                          valuePlaceholder="value"
                        />
                      </>
                    )}

                    {server.type === "stdio" && (
                      <>
                        <div className="mc-row">
                          <div className="mc-field" style={{ flex: 1 }}>
                            <label className="mc-label">Command</label>
                            <input
                              className="mc-input"
                              value={server.command ?? ""}
                              onChange={(e) => updateServer(server.id, { command: e.target.value })}
                              placeholder="uvx"
                            />
                          </div>
                          <div className="mc-field" style={{ flex: 2 }}>
                            <label className="mc-label">Arguments (space-separated)</label>
                            <input
                              className="mc-input"
                              value={server.args ?? ""}
                              onChange={(e) => updateServer(server.id, { args: e.target.value })}
                              placeholder="minimax-mcp --flag"
                            />
                          </div>
                        </div>
                        <KeyValueEditor
                          label="Environment Variables"
                          value={server.env ?? ""}
                          onChange={(val) => updateServer(server.id, { env: val })}
                          keyPlaceholder="VARIABLE_NAME"
                          valuePlaceholder="value"
                          secretValues
                        />
                      </>
                    )}

                    {/* Connection status (inline in edit form when failed) */}
                    {server.enabled && testStatus[server.id] && !testStatus[server.id].loading && !testStatus[server.id].ok && (
                      <div className="mc-test-error">
                        <CircleAlert size={14} />
                        <span>{testStatus[server.id].error}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add MCP Server */}
      {showAddPicker ? (
        <div className="add-picker">
          <div className="add-picker-label">Choose transport type:</div>
          <div className="add-picker-grid">
            <button className="add-picker-btn" onClick={() => addServer("http")}>HTTP</button>
            <button className="add-picker-btn" onClick={() => addServer("stdio")}>Stdio</button>
          </div>
          <button className="add-picker-cancel" onClick={() => setShowAddPicker(false)}>Cancel</button>
        </div>
      ) : (
        <div className="model-actions">
          <button className="model-add-btn" onClick={() => setShowAddPicker(true)}>
            <Plus size={16} /> Add MCP Server
          </button>
        </div>
      )}
    </div>
  );
}

// ── Tools Tab ──

const SEARCH_PROVIDERS = [
  { id: "", label: "None" },
  { id: "tavily", label: "Tavily" },
  { id: "brave", label: "Brave" },
];

const FETCH_PROVIDERS = [
  { id: "", label: "None" },
  { id: "jina", label: "Jina" },
  { id: "firecrawl", label: "Firecrawl" },
];

function ToolsTab() {
  const { dispatch } = useAppContext();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [originalTools, setOriginalTools] = useState<ServerConfig["tools"] | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [showSearchKey, setShowSearchKey] = useState(true);
  const [showFetchKey, setShowFetchKey] = useState(true);
  // Per-provider key cache: { tavily: "key1", brave: "key2", jina: "key3", ... }
  const [searchKeys, setSearchKeys] = useState<Record<string, string>>({});
  const [fetchKeys, setFetchKeys] = useState<Record<string, string>>({});

  useEffect(() => {
    getServerConfig().then((cfg) => {
      setConfig(cfg);
      setOriginalTools(cfg.tools);
      setShowSearchKey(!cfg.tools.search_api_key);
      setShowFetchKey(!cfg.tools.fetch_api_key);
      if (cfg.tools.search_provider && cfg.tools.search_api_key) {
        setSearchKeys((prev) => ({ ...prev, [cfg.tools.search_provider]: cfg.tools.search_api_key }));
      }
      if (cfg.tools.fetch_provider && cfg.tools.fetch_api_key) {
        setFetchKeys((prev) => ({ ...prev, [cfg.tools.fetch_provider]: cfg.tools.fetch_api_key }));
      }
    }).catch((e: Error) => setError(e.message));
  }, []);

  const isDirty = (() => {
    if (!config || !originalTools) return false;
    const t = config.tools;
    return t.search_provider !== originalTools.search_provider
      || t.search_api_key !== originalTools.search_api_key
      || t.fetch_provider !== originalTools.fetch_provider
      || t.fetch_api_key !== originalTools.fetch_api_key;
  })();

  const updateTools = (updates: Partial<ServerConfig["tools"]>) => {
    if (!config) return;
    setConfig({ ...config, tools: { ...config.tools, ...updates } });
    setSaved(false);
  };

  const switchSearchProvider = (provider: string) => {
    if (!config) return;
    // Save current key before switching
    if (config.tools.search_provider && config.tools.search_api_key) {
      setSearchKeys((prev) => ({ ...prev, [config.tools.search_provider]: config.tools.search_api_key }));
    }
    // Restore key for new provider
    const restoredKey = searchKeys[provider] || "";
    updateTools({ search_provider: provider, search_api_key: restoredKey });
    setShowSearchKey(!restoredKey);
  };

  const switchFetchProvider = (provider: string) => {
    if (!config) return;
    if (config.tools.fetch_provider && config.tools.fetch_api_key) {
      setFetchKeys((prev) => ({ ...prev, [config.tools.fetch_provider]: config.tools.fetch_api_key }));
    }
    const restoredKey = fetchKeys[provider] || "";
    updateTools({ fetch_provider: provider, fetch_api_key: restoredKey });
    setShowFetchKey(!restoredKey);
  };

  const handleSave = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateServerConfig(config);
      setConfig(updated);
      setOriginalTools(updated.tools);
      dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  }, [config, dispatch]);

  useSettingsDirty(isDirty, handleSave);

  if (!config) return <div className="settings-section"><p className="settings-hint">Loading configuration...</p></div>;

  const tools = config.tools;

  return (
    <div className="settings-section">
      <p className="settings-hint">
        Configure web search and page fetching providers for the agent.
      </p>

      {error && <div className="model-error">{error}</div>}

      {/* Web Search */}
      <div className="tools-group">
        <div className="tools-group-header">
          <Globe size={14} className="tools-group-icon" />
          <span className="tools-group-title">Web Search</span>
          <span className="tools-group-desc">Search the web for information</span>
        </div>
        <div className="tools-group-body">
          <div className="mc-field">
            <label className="mc-label">Provider</label>
            <div className="mc-pills">
              {SEARCH_PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  className={`mc-pill ${tools.search_provider === p.id ? "mc-pill--active" : ""}`}
                  onClick={() => switchSearchProvider(p.id)}
                  type="button"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          {tools.search_provider && (
            <div className="mc-field">
              <label className="mc-label">API Key <span className="tools-key-required">Required</span></label>
              <div className="mc-key-wrap">
                <input
                  className="mc-input mc-input--key"
                  type={showSearchKey ? "text" : "password"}
                  autoComplete="off"
                  data-1p-ignore
                  data-lpignore="true"
                  data-form-type="other"
                  value={tools.search_api_key}
                  onChange={(e) => updateTools({ search_api_key: e.target.value })}
                  placeholder={tools.search_provider === "tavily" ? "tvly-..." : "BSA..."}
                />
                <button
                  className="mc-key-toggle"
                  onClick={() => setShowSearchKey(!showSearchKey)}
                  title={showSearchKey ? "Hide" : "Show"}
                  type="button"
                >
                  {showSearchKey ? <Eye size={14} /> : <EyeOff size={14} />}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Web Fetch */}
      <div className="tools-group">
        <div className="tools-group-header">
          <ScrollText size={14} className="tools-group-icon" />
          <span className="tools-group-title">Web Fetch</span>
          <span className="tools-group-desc">Fetch and extract web page content</span>
        </div>
        <div className="tools-group-body">
          <div className="mc-field">
            <label className="mc-label">Provider</label>
            <div className="mc-pills">
              {FETCH_PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  className={`mc-pill ${tools.fetch_provider === p.id ? "mc-pill--active" : ""}`}
                  onClick={() => switchFetchProvider(p.id)}
                  type="button"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          {tools.fetch_provider && (
            <div className="mc-field">
              <label className="mc-label">
                API Key
                {tools.fetch_provider === "jina"
                  ? <span className="tools-key-hint">Optional — increases rate limit</span>
                  : <span className="tools-key-required">Required</span>
                }
              </label>
              <div className="mc-key-wrap">
                <input
                  className="mc-input mc-input--key"
                  type={showFetchKey ? "text" : "password"}
                  autoComplete="off"
                  data-1p-ignore
                  data-lpignore="true"
                  data-form-type="other"
                  value={tools.fetch_api_key}
                  onChange={(e) => updateTools({ fetch_api_key: e.target.value })}
                  placeholder={tools.fetch_provider === "jina" ? "jina_..." : "fc-..."}
                />
                <button
                  className="mc-key-toggle"
                  onClick={() => setShowFetchKey(!showFetchKey)}
                  title={showFetchKey ? "Hide" : "Show"}
                  type="button"
                >
                  {showFetchKey ? <Eye size={14} /> : <EyeOff size={14} />}
                </button>
              </div>
            </div>
          )}
          <p className="tools-fetch-note">* Requires a summarizer model — configure in Model settings</p>
        </div>
      </div>

      {/* Save */}
      <div className="model-save-bar">
        {isDirty && !saved && <span className="model-unsaved-hint">Unsaved changes</span>}
        <button
          className={`model-save-btn ${saved ? "saved" : ""}`}
          onClick={handleSave}
          disabled={saving || (!isDirty && !saved)}
        >
          {saving ? (
            <><Loader2 size={14} className="model-save-spinner" /> Applying...</>
          ) : saved ? (
            <><Check size={14} /> Saved</>
          ) : isDirty ? (
            "Save & Apply"
          ) : (
            "No Changes"
          )}
        </button>
      </div>
    </div>
  );
}

// ── Custom Dropdown ──

function CustomSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string; detail?: string }[];
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div className="cs" ref={ref}>
      <button className="cs-trigger" onClick={() => setOpen(!open)} type="button">
        <span className="cs-trigger-label">{selected?.label ?? "Select..."}</span>
        <ChevronDown size={14} className={`cs-trigger-chevron ${open ? "cs-trigger-chevron--open" : ""}`} />
      </button>
      {open && (
        <div className="dd-panel cs-dropdown">
          {options.map((o) => {
            const active = o.value === value;
            return (
              <button
                key={o.value}
                className={`dd-item ${active ? "dd-item--active" : ""}`}
                onClick={() => { onChange(o.value); setOpen(false); }}
                type="button"
              >
                <div className="cs-option-content">
                  <span className="dd-item-label">{o.label}</span>
                  {o.detail && <span className="dd-item-detail">{o.detail}</span>}
                </div>
                {active && <Check size={14} strokeWidth={2.5} className="dd-item-check" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Subagent Tab ──

function SubagentTab() {
  const { dispatch } = useAppContext();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  // Local string state for each agent's tools input to avoid comma-eating on keystroke
  const [toolsText, setToolsText] = useState<Record<string, string>>({});

  useEffect(() => {
    getServerConfig().then((cfg) => {
      setConfig(cfg);
      // Initialize toolsText from loaded config
      const initial: Record<string, string> = {};
      for (const a of cfg.agents ?? []) {
        initial[a.id] = a.tools.join(", ");
      }
      setToolsText(initial);
    }).catch((e: Error) => setError(e.message));
  }, []);

  const markDirty = () => { setDirty(true); setSaved(false); };

  const updateAgent = (id: string, updates: Partial<AgentConfig>) => {
    if (!config) return;
    setConfig({
      ...config,
      agents: (config.agents ?? []).map((a) => (a.id === id ? { ...a, ...updates } : a)),
    });
    markDirty();
  };

  const addAgent = () => {
    if (!config) return;
    const newAgent: AgentConfig = {
      id: crypto.randomUUID(),
      name: "",
      description: "",
      system_prompt: "",
      tools: [],
      model_id: "",
      enabled: false,
    };
    setConfig({ ...config, agents: [...(config.agents ?? []), newAgent] });
    setToolsText((prev) => ({ ...prev, [newAgent.id]: "" }));
    setExpandedId(newAgent.id);
    markDirty();
  };

  const deleteAgent = (id: string) => {
    if (!config) return;
    setConfig({ ...config, agents: (config.agents ?? []).filter((a) => a.id !== id) });
    setToolsText((prev) => { const next = { ...prev }; delete next[id]; return next; });
    setConfirmingDeleteId(null);
    if (expandedId === id) setExpandedId(null);
    markDirty();
  };

  const handleSave = useCallback(async () => {
    if (!config) return;
    // Flush any pending toolsText into the config before saving
    const flushed = {
      ...config,
      agents: (config.agents ?? []).map((a) => {
        const raw = toolsText[a.id];
        if (raw === undefined) return a;
        return { ...a, tools: raw.split(/[,\n]/).map((t) => t.trim()).filter(Boolean) };
      }),
    };
    setSaving(true);
    setError("");
    try {
      const updated = await updateServerConfig(flushed);
      setConfig(updated);
      dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
      const refreshed: Record<string, string> = {};
      for (const a of updated.agents ?? []) {
        refreshed[a.id] = a.tools.join(", ");
      }
      setToolsText(refreshed);
      setSaved(true);
      setDirty(false);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  }, [config, toolsText, dispatch]);

  useSettingsDirty(dirty, handleSave);

  if (!config) return <div className="settings-section"><p className="settings-hint">Loading configuration...</p></div>;

  const agents = config.agents ?? [];
  const models = config.models ?? [];

  return (
    <div className="settings-section">
      <p className="settings-hint">
        Define specialized subagents that the main agent can delegate tasks to.
      </p>

      {error && <div className="model-error">{error}</div>}

      <div className="ml-list">
        {agents.map((agent) => {
          const expanded = expandedId === agent.id;

          return (
            <div key={agent.id} className={`ml-item ${expanded ? "ml-item--expanded" : ""}`}>
              <div className="ml-row" onClick={() => setExpandedId(expanded ? null : agent.id)}>
                <div className="ml-row-info">
                  <div className="ml-row-top">
                    <span className="ml-row-name">{agent.name || "Untitled agent"}</span>
                  </div>
                  <div className="ml-row-meta">
                    {agent.description || "No description"}
                  </div>
                </div>
                <div className="ml-row-actions">
                  <label className="mcp-toggle" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={agent.enabled}
                      onChange={(e) => updateAgent(agent.id, { enabled: e.target.checked })}
                    />
                    <span className="mcp-toggle-slider" />
                  </label>
                  <button
                    className="settings-del"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirmingDeleteId === agent.id) {
                        deleteAgent(agent.id);
                      } else {
                        setConfirmingDeleteId(agent.id);
                      }
                    }}
                    title={confirmingDeleteId === agent.id ? "Click again to confirm" : "Delete"}
                  >
                    <Trash2 size={14} />
                  </button>
                  {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </div>
              </div>

              {confirmingDeleteId === agent.id && !expanded && (
                <div className="ml-confirm-bar">
                  <span>Delete this agent?</span>
                  <button className="mc-confirm-yes" onClick={() => deleteAgent(agent.id)}>Delete</button>
                  <button className="mc-confirm-no" onClick={() => setConfirmingDeleteId(null)}>Cancel</button>
                </div>
              )}

              <div className={`ml-edit-wrap ${expanded ? "ml-edit-wrap--open" : ""}`}>
                <div className="ml-edit">
                  <div className="ml-edit-inner">
                    <div className="mc-row">
                      <div className="mc-field" style={{ flex: 1 }}>
                        <label className="mc-label">Name</label>
                        <input
                          className="mc-input"
                          value={agent.name}
                          onChange={(e) => updateAgent(agent.id, { name: e.target.value })}
                          placeholder="e.g. code-reviewer"
                        />
                      </div>
                      <div className="mc-field" style={{ flex: 1 }}>
                        <label className="mc-label">Model</label>
                        <CustomSelect
                          value={agent.model_id}
                          options={[
                            { value: "", label: "Default" },
                            ...models.map((m) => ({
                              value: m.id,
                              label: m.display_name || m.model || "Untitled",
                            })),
                          ]}
                          onChange={(val) => updateAgent(agent.id, { model_id: val })}
                        />
                      </div>
                    </div>

                    <div className="mc-field">
                      <label className="mc-label">Description</label>
                      <input
                        className="mc-input"
                        value={agent.description}
                        onChange={(e) => updateAgent(agent.id, { description: e.target.value })}
                        placeholder="What this agent does (shown to the main agent)"
                      />
                    </div>

                    <div className="mc-field">
                      <label className="mc-label">Tools (comma or newline separated)</label>
                      <textarea
                        className="mc-input"
                        value={toolsText[agent.id] ?? agent.tools.join(", ")}
                        onChange={(e) => {
                          setToolsText((prev) => ({ ...prev, [agent.id]: e.target.value }));
                          markDirty();
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            e.currentTarget.blur();
                          }
                        }}
                        onBlur={() => {
                          const raw = toolsText[agent.id] ?? "";
                          const parsed = raw.split(/[,\n]/).map((t) => t.trim()).filter(Boolean);
                          updateAgent(agent.id, { tools: parsed });
                          setToolsText((prev) => ({ ...prev, [agent.id]: parsed.join(", ") }));
                        }}
                        placeholder="e.g. Read, Grep, Glob (empty = all tools)"
                        rows={2}
                        style={{ resize: "vertical", fontFamily: "inherit" }}
                      />
                    </div>

                    <div className="mc-field">
                      <label className="mc-label">System Prompt</label>
                      <textarea
                        className="mc-input"
                        value={agent.system_prompt}
                        onChange={(e) => updateAgent(agent.id, { system_prompt: e.target.value })}
                        placeholder="Custom instructions for this agent..."
                        rows={4}
                        style={{ resize: "vertical", fontFamily: "inherit" }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="model-actions">
        <button className="model-add-btn" onClick={addAgent}>
          <Plus size={16} /> Add Subagent
        </button>
      </div>

      <div className="model-save-bar">
        {dirty && !saved && <span className="model-unsaved-hint">Unsaved changes</span>}
        <button
          className={`model-save-btn ${saved ? "saved" : ""}`}
          onClick={handleSave}
          disabled={saving || (!dirty && !saved)}
        >
          {saving ? (
            <><Loader2 size={14} className="model-save-spinner" /> Applying...</>
          ) : saved ? (
            <><Check size={14} /> Saved</>
          ) : dirty ? (
            "Save & Apply"
          ) : (
            "No Changes"
          )}
        </button>
      </div>
    </div>
  );
}

function SandboxTab() {
  const { dispatch } = useAppContext();
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [originalKey, setOriginalKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [showKey, setShowKey] = useState(true);
  const [folders, setFolders] = useState<RecentFolder[]>(() => loadRecentFolders());

  useEffect(() => {
    getServerConfig().then((cfg) => {
      setConfig(cfg);
      setOriginalKey(cfg.sandbox.e2b_api_key);
      setShowKey(!cfg.sandbox.e2b_api_key);
    }).catch((e: Error) => setError(e.message));
  }, []);

  const isDirty = config ? config.sandbox.e2b_api_key !== originalKey : false;

  const handleSave = useCallback(async () => {
    if (!config) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateServerConfig(config);
      setConfig(updated);
      setOriginalKey(updated.sandbox.e2b_api_key);
      dispatch({ type: "SET_SERVER_CONFIG", payload: updated });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSaving(false);
    }
  }, [config, dispatch]);

  useSettingsDirty(isDirty, handleSave);

  const toggleFolderPermission = (path: string) => {
    const updated = folders.map((f) =>
      f.path === path ? { ...f, alwaysAllowed: !f.alwaysAllowed } : f
    );
    setFolders(updated);
    saveRecentFolders(updated);
  };

  const removeFolder = (path: string) => {
    const updated = folders.filter((f) => f.path !== path);
    setFolders(updated);
    saveRecentFolders(updated);
  };

  if (!config) return <div className="settings-section"><p className="settings-hint">Loading configuration...</p></div>;

  const e2bConfigured = !!config.sandbox.e2b_api_key;

  return (
    <div className="settings-section">
      {error && <div className="model-error">{error}</div>}

      {/* ── E2B Sandbox (Chat mode) ── */}
      <div className="sb-card">
        <div className="sb-card-header">
          <div className="sb-card-icon"><Server size={18} /></div>
          <div className="sb-card-title-group">
            <div className="sb-card-title-row">
              <span className="sb-card-title">E2B Sandbox</span>
              <span className="sb-card-badge sb-card-badge--chat">Chat mode</span>
            </div>
            <span className="sb-card-desc">Cloud sandbox — runs agent code remotely via E2B</span>
          </div>
          <span className={`sb-card-status ${e2bConfigured ? "sb-card-status--ok" : "sb-card-status--warn"}`}>
            {e2bConfigured
              ? <><CircleCheck size={14} /> Configured</>
              : <><CircleAlert size={14} /> Not configured</>}
          </span>
        </div>
        <div className="sb-card-body">
          <div className="mc-field">
            <label className="mc-label">API Key</label>
            <div className="mc-key-wrap">
              <input
                className="mc-input mc-input--key"
                type={showKey ? "text" : "password"}
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                data-form-type="other"
                placeholder="e2b_..."
                value={config.sandbox.e2b_api_key}
                onChange={(e) => {
                  setConfig({ ...config, sandbox: { ...config.sandbox, e2b_api_key: e.target.value } });
                  setSaved(false);
                }}
              />
              <button
                className="mc-key-toggle"
                type="button"
                onClick={() => setShowKey(!showKey)}
                title={showKey ? "Hide" : "Show"}
              >
                {showKey ? <Eye size={14} /> : <EyeOff size={14} />}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Virtual Machine (Cowork mode) ── */}
      <div className="sb-card">
        <div className="sb-card-header">
          <div className="sb-card-icon"><Monitor size={18} /></div>
          <div className="sb-card-title-group">
            <div className="sb-card-title-row">
              <span className="sb-card-title">Virtual Machine</span>
              <span className="sb-card-badge sb-card-badge--cowork">Cowork mode</span>
              <span className="sb-card-badge sb-card-badge--platform">macOS only</span>
            </div>
            <span className="sb-card-desc">Local VM sandbox — runs agent code securely on your machine</span>
          </div>
          <span className="sb-card-status sb-card-status--ok">
            <CircleCheck size={14} /> Ready
          </span>
        </div>
        <div className="sb-card-body">
          <div className="vm-folder-list">
            <label className="mc-label" style={{ marginBottom: 2 }}>Recent folders</label>
            {folders.map((folder) => (
              <div key={folder.path} className="vm-folder-row">
                <FolderOpen size={14} className="vm-folder-icon" />
                <span className="vm-folder-path" title={folder.path}><bdo dir="ltr">{folder.path}</bdo></span>
                <CustomSelect
                  value={folder.alwaysAllowed ? "allow" : "ask"}
                  options={[
                    { value: "allow", label: "Allow" },
                    { value: "ask", label: "Ask" },
                  ]}
                  onChange={() => toggleFolderPermission(folder.path)}
                />
                <button
                  className="settings-del vm-folder-remove"
                  onClick={() => removeFolder(folder.path)}
                  title="Remove folder"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
            <button
              className="vm-folder-add"
              type="button"
              onClick={async () => {
                const path = await browseFolder();
                if (path) {
                  const updated = [
                    { path, alwaysAllowed: false },
                    ...folders.filter((f) => f.path !== path),
                  ].slice(0, 8);
                  setFolders(updated);
                  saveRecentFolders(updated);
                }
              }}
            >
              <FolderPlus size={14} />
              <span>Add a folder</span>
            </button>
          </div>
        </div>
      </div>

      <div className="model-save-bar">
        {isDirty && !saved && <span className="model-unsaved-hint">Unsaved changes</span>}
        <button
          className={`model-save-btn ${saved ? "saved" : ""}`}
          onClick={handleSave}
          disabled={saving || (!isDirty && !saved)}
        >
          {saving ? (
            <><Loader2 size={14} className="model-save-spinner" /> Applying...</>
          ) : saved ? (
            <><Check size={14} /> Saved</>
          ) : isDirty ? (
            "Save & Apply"
          ) : (
            "No Changes"
          )}
        </button>
      </div>
    </div>
  );
}

// ── Skills Tab ──

function SkillsTab() {
  const [publicSkills, setPublicSkills] = useState<string[]>([]);
  const [userSkills, setUserSkills] = useState<string[]>([]);
  const [exampleSkills, setExampleSkills] = useState<string[]>([]);
  const [disabledSkills, setDisabledSkills] = useState<Set<string>>(new Set());
  const [errorPopup, setErrorPopup] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState<{ name: string; builtin: boolean } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const showError = (msg: string) => setErrorPopup(msg);

  const loadSkills = useCallback(async () => {
    try {
      const data = await listSkills();
      setPublicSkills(data.public);
      setUserSkills(data.user);
      setExampleSkills(data.examples ?? []);
      setDisabledSkills(new Set(data.disabled));
    } catch (e: unknown) {
      showError(e instanceof Error ? e.message : "Failed to load skills");
    }
  }, []);

  useEffect(() => { loadSkills(); }, [loadSkills]);

  const doUpload = async (file: File) => {
    if (!file.name.endsWith(".zip") && !file.name.endsWith(".skill")) {
      showError("Only .zip and .skill files are accepted.");
      return;
    }
    setUploading(true);
    try {
      await uploadSkill(file);
      await loadSkills();
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) doUpload(file);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) doUpload(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleToggle = async (name: string, enabled: boolean) => {
    // Optimistic update
    setDisabledSkills((prev) => {
      const next = new Set(prev);
      if (enabled) next.delete(name); else next.add(name);
      return next;
    });
    try {
      await toggleSkill(name, enabled);
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Toggle failed");
      await loadSkills(); // revert on failure
    }
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    const { name } = deleteConfirm;
    setDeleteConfirm(null);
    try {
      await deleteSkill(name);
      await loadSkills();
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleInstall = async (name: string) => {
    try {
      await installSkill(name);
      await loadSkills();
    } catch (err: unknown) {
      showError(err instanceof Error ? err.message : "Install failed");
    }
  };

  return (
    <div className="settings-section">
      <p className="settings-hint">
        Skills are reusable instruction sets that guide Agent on specific tasks — like creating documents, presentations, or spreadsheets.
      </p>

      {/* Error popup dialog */}
      {errorPopup && (
        <div className="settings-confirm-overlay" onClick={() => setErrorPopup("")}>
          <div className="settings-confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="skills-error-header">
              <TriangleAlert size={18} className="skills-error-icon" />
              <h3 className="settings-confirm-title">Error</h3>
            </div>
            <p className="settings-confirm-body">{errorPopup}</p>
            <div className="settings-confirm-actions">
              <button className="settings-confirm-btn settings-confirm-btn--save" onClick={() => setErrorPopup("")}>
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      {deleteConfirm && (
        <div className="settings-confirm-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="settings-confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 className="settings-confirm-title">Remove "{deleteConfirm.name}"?</h3>
            <p className="settings-confirm-body">
              {deleteConfirm.builtin
                ? "This skill will be moved to Examples. You can always install it back later."
                : "This will permanently remove the skill. This action cannot be undone."}
            </p>
            <div className="settings-confirm-actions">
              <button className="settings-confirm-btn" onClick={() => setDeleteConfirm(null)}>
                Cancel
              </button>
              <button className="settings-confirm-btn settings-confirm-btn--discard" onClick={confirmDelete}>
                Remove
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Example skills */}
      {exampleSkills.length > 0 && (
        <div className="skills-group">
          <div className="skills-group-label">Examples</div>
          <div className="skills-list">
            {exampleSkills.every((name) => publicSkills.includes(name)) ? (
              <p className="settings-hint skills-empty">All example skills are installed under Built-in.</p>
            ) : (
              exampleSkills.filter((name) => !publicSkills.includes(name)).map((name) => (
                <div key={name} className="skills-item skills-item--example">
                  <Package size={14} className="skills-item-icon" />
                  <span className="skills-item-name">{name}</span>
                  <button
                    className="skills-item-install"
                    onClick={() => handleInstall(name)}
                    title="Install skill"
                  >
                    <Download size={13} />
                    <span>Install</span>
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Built-in skills */}
      {publicSkills.length > 0 && (
        <div className="skills-group">
          <div className="skills-group-label">Built-in</div>
          <div className="skills-list">
            {publicSkills.map((name) => (
              <div key={name} className={`skills-item ${disabledSkills.has(name) ? "skills-item--disabled" : ""}`}>
                <Package size={14} className="skills-item-icon" />
                <span className="skills-item-name">{name}</span>
                <button
                  className={`skills-toggle ${disabledSkills.has(name) ? "" : "skills-toggle--on"}`}
                  onClick={() => handleToggle(name, disabledSkills.has(name))}
                  title={disabledSkills.has(name) ? "Enable skill" : "Disable skill"}
                />
                <button
                  className="settings-del"
                  onClick={() => { deleteSkill(name).then(() => loadSkills()).catch((err: unknown) => showError(err instanceof Error ? err.message : "Delete failed")); }}
                  title="Remove skill"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* User skills */}
      <div className="skills-group">
        <div className="skills-group-label">Custom</div>
        <div className="skills-list">
          {userSkills.map((name) => (
            <div key={name} className={`skills-item ${disabledSkills.has(name) ? "skills-item--disabled" : ""}`}>
              <Package size={14} className="skills-item-icon" />
              <span className="skills-item-name">{name}</span>
              <button
                className={`skills-toggle ${disabledSkills.has(name) ? "" : "skills-toggle--on"}`}
                onClick={() => handleToggle(name, disabledSkills.has(name))}
                title={disabledSkills.has(name) ? "Enable skill" : "Disable skill"}
              />
              <button
                className="settings-del"
                onClick={() => setDeleteConfirm({ name, builtin: false })}
                title="Remove skill"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {userSkills.length === 0 && (
            <p className="settings-hint skills-empty">No custom skills installed.</p>
          )}
        </div>
      </div>

      {/* Upload drop zone */}
      <input
        ref={fileRef}
        type="file"
        accept=".zip,.skill"
        onChange={handleFileInput}
        style={{ display: "none" }}
      />
      <div
        className={`skills-dropzone ${dragOver ? "skills-dropzone--active" : ""}`}
        onClick={() => !uploading && fileRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        {uploading ? (
          <><Loader2 size={16} className="model-save-spinner" /> Uploading...</>
        ) : (
          <>
            <Upload size={16} />
            <span>Drop .zip or .skill file here, or click to browse</span>
          </>
        )}
        <span className="skills-dropzone-hint">SKILL.md required — name (lowercase, hyphens only) must match directory name</span>
      </div>
    </div>
  );
}
