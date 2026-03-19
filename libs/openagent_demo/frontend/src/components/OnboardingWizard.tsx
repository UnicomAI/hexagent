import { useState, useEffect } from "react";
import {
  Eye, EyeOff, ArrowRight, ChevronDown, ChevronRight,
  Sparkles, Globe, ScrollText, Server, Monitor, Check,
} from "lucide-react";
import { getServerConfig, updateServerConfig } from "../api";
import type { ServerConfig, ModelConfig } from "../api";
import { useAppContext } from "../store";

interface OnboardingWizardProps {
  open: boolean;
  onComplete: () => void;
}

// ---------------------------------------------------------------------------
// Provider presets
// ---------------------------------------------------------------------------

interface ProviderOption {
  id: string;
  label: string;
  base_url: string;
  provider: string;
  placeholder_model: string;
  placeholder_key: string;
}

const PROVIDERS: ProviderOption[] = [
  {
    id: "openai",
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    provider: "openai",
    placeholder_model: "gpt-4.1",
    placeholder_key: "sk-...",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    base_url: "https://api.anthropic.com",
    provider: "anthropic",
    placeholder_model: "claude-sonnet-4-20250514",
    placeholder_key: "sk-ant-...",
  },
  {
    id: "custom",
    label: "OpenAI-Compatible",
    base_url: "",
    provider: "deepseek",
    placeholder_model: "model-name",
    placeholder_key: "sk-...",
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate a human-friendly display name from a model ID. */
function autoDisplayName(modelId: string): string {
  if (!modelId) return "";
  // Strip provider prefix (e.g. "anthropic/claude-sonnet-4" → "claude-sonnet-4")
  const base = modelId.includes("/") ? modelId.split("/").pop()! : modelId;
  return base
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// ---------------------------------------------------------------------------
// Step definitions
// ---------------------------------------------------------------------------

type Step = "welcome" | "model" | "summarizer" | "tools" | "compute" | "done";

const STEPS: Step[] = ["welcome", "model", "summarizer", "tools", "compute", "done"];

function stepIndex(s: Step): number {
  return STEPS.indexOf(s);
}

// ---------------------------------------------------------------------------

export default function OnboardingWizard({ open, onComplete }: OnboardingWizardProps) {
  const { dispatch } = useAppContext();
  const [step, setStep] = useState<Step>("welcome");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [config, setConfig] = useState<ServerConfig | null>(null);

  // ── Step 1: Model ──
  const [selectedProvider, setSelectedProvider] = useState<ProviderOption | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [modelId, setModelId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // ── Step 2: Summarizer ──
  const [sumProvider, setSumProvider] = useState<ProviderOption | null>(null);
  const [sumApiKey, setSumApiKey] = useState("");
  const [sumModelId, setSumModelId] = useState("");
  const [sumDisplayName, setSumDisplayName] = useState("");
  const [sumBaseUrl, setSumBaseUrl] = useState("");
  const [showSumKey, setShowSumKey] = useState(false);
  const [sumSameAsMain, setSumSameAsMain] = useState(true);
  const [sumShowAdvanced, setSumShowAdvanced] = useState(false);

  // ── Step 3: Web Tools ──
  const [searchProvider, setSearchProvider] = useState("");
  const [searchKey, setSearchKey] = useState("");
  const [fetchProvider, setFetchProvider] = useState("");
  const [fetchKey, setFetchKey] = useState("");
  const [showSearchKey, setShowSearchKey] = useState(false);
  const [showFetchKey, setShowFetchKey] = useState(false);

  // ── Step 4: Compute ──
  const [e2bKey, setE2bKey] = useState("");
  const [showE2bKey, setShowE2bKey] = useState(false);

  // Load server config once
  useEffect(() => {
    if (open) {
      getServerConfig().then(setConfig).catch(() => {});
    }
  }, [open]);

  if (!open) return null;

  // ── Navigation ──
  const goNext = () => {
    const idx = stepIndex(step);
    if (idx < STEPS.length - 1) {
      setError("");
      setStep(STEPS[idx + 1]);
    }
  };
  const goBack = () => {
    const idx = stepIndex(step);
    if (idx > 0) {
      setError("");
      setStep(STEPS[idx - 1]);
    }
  };

  // ── Save all config at the end ──
  const handleFinish = async () => {
    if (!config) return;
    if (!selectedProvider || !apiKey.trim() || !modelId.trim()) {
      setError("Please go back and configure your AI model first");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const mainModel: ModelConfig = {
        id: crypto.randomUUID(),
        display_name: displayName || autoDisplayName(modelId),
        api_key: apiKey,
        base_url: baseUrl || selectedProvider.base_url,
        model: modelId,
        provider: selectedProvider.provider,
        context_window: 200000,
        supported_modalities: ["text"],
      };

      const models: ModelConfig[] = [mainModel];
      let fastModelId = "";

      // Summarizer model
      if (!sumSameAsMain && sumProvider && sumApiKey.trim() && sumModelId.trim()) {
        const sumModel: ModelConfig = {
          id: crypto.randomUUID(),
          display_name: sumDisplayName || autoDisplayName(sumModelId),
          api_key: sumApiKey,
          base_url: sumBaseUrl || sumProvider.base_url,
          model: sumModelId,
          provider: sumProvider.provider,
          context_window: 200000,
          supported_modalities: ["text"],
        };
        models.push(sumModel);
        fastModelId = sumModel.id;
      }

      const updated: ServerConfig = {
        ...config,
        models,
        main_model_id: mainModel.id,
        fast_model_id: fastModelId,
        tools: {
          search_provider: searchProvider,
          search_api_key: searchKey,
          fetch_provider: fetchProvider,
          fetch_api_key: fetchKey,
        },
        sandbox: {
          e2b_api_key: e2bKey,
        },
      };

      const saved = await updateServerConfig(updated);
      dispatch({ type: "SET_SERVER_CONFIG", payload: saved });
      onComplete();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  // ── Validation for model step ──
  const isCustomProvider = selectedProvider?.id === "custom";
  const canProceedFromModel =
    selectedProvider &&
    apiKey.trim() &&
    modelId.trim() &&
    (!isCustomProvider || baseUrl.trim());

  return (
    <div className="setup-overlay">
      <div className="setup-modal">

        {/* ── Welcome: provider picker ── */}
        {step === "welcome" && (
          <div className="setup-step">
            <div className="setup-icon">
              <Sparkles size={28} />
            </div>
            <h2 className="setup-title">Welcome to OpenAgent</h2>
            <p className="setup-subtitle">Connect an AI model to get started</p>

            <div className="setup-providers">
              {PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  className="setup-provider-btn"
                  onClick={() => {
                    setSelectedProvider(p);
                    setBaseUrl(p.base_url);
                    if (p.id !== "custom") setDisplayName("");
                    setError("");
                    setStep("model");
                  }}
                >
                  <span className="setup-provider-name">{p.label}</span>
                  <ArrowRight size={14} className="setup-provider-arrow" />
                </button>
              ))}
            </div>

            <p className="setup-footer">
              You can add more models later in Settings.
            </p>
          </div>
        )}

        {/* ── Step 1: Model credentials ── */}
        {step === "model" && selectedProvider && (
          <div className="setup-step">
            <div className="setup-step-header">
              <Sparkles size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">Configure {selectedProvider.label}</h2>
                <p className="setup-subtitle">Enter your API credentials</p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-form">
              <div className="setup-field">
                <label className="setup-label">API Key</label>
                <div className="setup-key-wrap">
                  <input
                    className="setup-input setup-input--key"
                    type={showKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={selectedProvider.placeholder_key}
                    autoFocus
                  />
                  <button
                    className="setup-key-toggle"
                    onClick={() => setShowKey(!showKey)}
                    type="button"
                  >
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              <div className="setup-field">
                <label className="setup-label">Model ID</label>
                <input
                  className="setup-input"
                  value={modelId}
                  onChange={(e) => {
                    setModelId(e.target.value);
                    if (!displayName || displayName === autoDisplayName(modelId)) {
                      setDisplayName(autoDisplayName(e.target.value));
                    }
                  }}
                  placeholder={selectedProvider.placeholder_model}
                />
              </div>

              {/* OpenAI-Compatible: base URL and display name are required */}
              {isCustomProvider && (
                <>
                  <div className="setup-field">
                    <label className="setup-label">Base URL</label>
                    <input
                      className="setup-input"
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder="https://api.example.com/v1"
                    />
                  </div>
                  <div className="setup-field">
                    <label className="setup-label">Display Name</label>
                    <input
                      className="setup-input"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder={autoDisplayName(modelId) || "My Model"}
                    />
                  </div>
                </>
              )}

              {/* OpenAI / Anthropic: advanced is collapsible */}
              {!isCustomProvider && (
                <>
                  <button
                    className="setup-advanced-toggle"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    type="button"
                  >
                    {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    Advanced
                  </button>

                  {showAdvanced && (
                    <div className="setup-advanced">
                      <div className="setup-field">
                        <label className="setup-label">Base URL</label>
                        <input
                          className="setup-input"
                          value={baseUrl}
                          onChange={(e) => setBaseUrl(e.target.value)}
                          placeholder={selectedProvider.base_url}
                        />
                      </div>
                      <div className="setup-field">
                        <label className="setup-label">Display Name</label>
                        <input
                          className="setup-input"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          placeholder={autoDisplayName(modelId) || "My Model"}
                        />
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={() => setStep("welcome")}>Back</button>
              <button
                className="setup-btn setup-btn--primary"
                onClick={goNext}
                disabled={!canProceedFromModel}
              >
                Next <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2: Summarizer ── */}
        {step === "summarizer" && (
          <div className="setup-step">
            <div className="setup-step-header">
              <ScrollText size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">Summarizer model</h2>
                <p className="setup-subtitle">
                  A fast model for web page summarization. Can be the same as your main model or a cheaper/faster one.
                </p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-field">
              <div className="setup-pill-group">
                <button
                  className={`setup-pill ${sumSameAsMain ? "setup-pill--active" : ""}`}
                  onClick={() => setSumSameAsMain(true)}
                  type="button"
                >
                  Same as main model
                </button>
                <button
                  className={`setup-pill ${!sumSameAsMain ? "setup-pill--active" : ""}`}
                  onClick={() => setSumSameAsMain(false)}
                  type="button"
                >
                  Different model
                </button>
              </div>
            </div>

            {!sumSameAsMain && (
              <div className="setup-form">
                <div className="setup-field">
                  <label className="setup-label">Provider</label>
                  <div className="setup-pill-group">
                    {PROVIDERS.map((p) => (
                      <button
                        key={p.id}
                        className={`setup-pill ${sumProvider?.id === p.id ? "setup-pill--active" : ""}`}
                        onClick={() => {
                          setSumProvider(p);
                          setSumBaseUrl(p.base_url);
                          if (p.id !== "custom") setSumDisplayName("");
                        }}
                        type="button"
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>

                {sumProvider && (
                  <>
                    <div className="setup-field">
                      <label className="setup-label">API Key</label>
                      <div className="setup-key-wrap">
                        <input
                          className="setup-input setup-input--key"
                          type={showSumKey ? "text" : "password"}
                          value={sumApiKey}
                          onChange={(e) => setSumApiKey(e.target.value)}
                          placeholder={sumProvider.placeholder_key}
                        />
                        <button
                          className="setup-key-toggle"
                          onClick={() => setShowSumKey(!showSumKey)}
                          type="button"
                        >
                          {showSumKey ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    <div className="setup-field">
                      <label className="setup-label">Model ID</label>
                      <input
                        className="setup-input"
                        value={sumModelId}
                        onChange={(e) => {
                          setSumModelId(e.target.value);
                          if (!sumDisplayName || sumDisplayName === autoDisplayName(sumModelId)) {
                            setSumDisplayName(autoDisplayName(e.target.value));
                          }
                        }}
                        placeholder={sumProvider.placeholder_model}
                      />
                    </div>

                    {/* OpenAI-Compatible: show base URL and display name inline */}
                    {sumProvider.id === "custom" && (
                      <>
                        <div className="setup-field">
                          <label className="setup-label">Base URL</label>
                          <input
                            className="setup-input"
                            value={sumBaseUrl}
                            onChange={(e) => setSumBaseUrl(e.target.value)}
                            placeholder="https://api.example.com/v1"
                          />
                        </div>
                        <div className="setup-field">
                          <label className="setup-label">Display Name</label>
                          <input
                            className="setup-input"
                            value={sumDisplayName}
                            onChange={(e) => setSumDisplayName(e.target.value)}
                            placeholder={autoDisplayName(sumModelId) || "Fast Model"}
                          />
                        </div>
                      </>
                    )}

                    {/* OpenAI / Anthropic: collapsible advanced */}
                    {sumProvider.id !== "custom" && (
                      <>
                        <button
                          className="setup-advanced-toggle"
                          onClick={() => setSumShowAdvanced(!sumShowAdvanced)}
                          type="button"
                        >
                          {sumShowAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          Advanced
                        </button>

                        {sumShowAdvanced && (
                          <div className="setup-advanced">
                            <div className="setup-field">
                              <label className="setup-label">Base URL</label>
                              <input
                                className="setup-input"
                                value={sumBaseUrl}
                                onChange={(e) => setSumBaseUrl(e.target.value)}
                                placeholder={sumProvider.base_url}
                              />
                            </div>
                            <div className="setup-field">
                              <label className="setup-label">Display Name</label>
                              <input
                                className="setup-input"
                                value={sumDisplayName}
                                onChange={(e) => setSumDisplayName(e.target.value)}
                                placeholder={autoDisplayName(sumModelId) || "Fast Model"}
                              />
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>
            )}

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>Back</button>
              <button className="setup-btn setup-btn--primary" onClick={goNext}>
                Next <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Web Tools ── */}
        {step === "tools" && (
          <div className="setup-step">
            <div className="setup-step-header">
              <Globe size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">Web search & fetch</h2>
                <p className="setup-subtitle">
                  Let the agent search the web and read pages. Optional — you can configure these later.
                </p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-form">
              {/* Web Search */}
              <div className="setup-tool-group">
                <div className="setup-tool-header">
                  <Globe size={14} />
                  <span>Web Search</span>
                </div>
                <div className="setup-field">
                  <label className="setup-label">Provider</label>
                  <div className="setup-pill-group">
                    {[
                      { id: "", label: "None" },
                      { id: "tavily", label: "Tavily" },
                      { id: "brave", label: "Brave" },
                    ].map((p) => (
                      <button
                        key={p.id}
                        className={`setup-pill ${searchProvider === p.id ? "setup-pill--active" : ""}`}
                        onClick={() => { setSearchProvider(p.id); if (!p.id) setSearchKey(""); }}
                        type="button"
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                {searchProvider && (
                  <div className="setup-field">
                    <label className="setup-label">API Key</label>
                    <div className="setup-key-wrap">
                      <input
                        className="setup-input setup-input--key"
                        type={showSearchKey ? "text" : "password"}
                        value={searchKey}
                        onChange={(e) => setSearchKey(e.target.value)}
                        placeholder={`${searchProvider} API key`}
                      />
                      <button className="setup-key-toggle" onClick={() => setShowSearchKey(!showSearchKey)} type="button">
                        {showSearchKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="setup-divider" />

              {/* Web Fetch */}
              <div className="setup-tool-group">
                <div className="setup-tool-header">
                  <ScrollText size={14} />
                  <span>Web Fetch</span>
                </div>
                <div className="setup-field">
                  <label className="setup-label">Provider</label>
                  <div className="setup-pill-group">
                    {[
                      { id: "", label: "None" },
                      { id: "jina", label: "Jina" },
                      { id: "firecrawl", label: "Firecrawl" },
                    ].map((p) => (
                      <button
                        key={p.id}
                        className={`setup-pill ${fetchProvider === p.id ? "setup-pill--active" : ""}`}
                        onClick={() => { setFetchProvider(p.id); if (!p.id) setFetchKey(""); }}
                        type="button"
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
                {fetchProvider && (
                  <div className="setup-field">
                    <label className="setup-label">API Key</label>
                    <div className="setup-key-wrap">
                      <input
                        className="setup-input setup-input--key"
                        type={showFetchKey ? "text" : "password"}
                        value={fetchKey}
                        onChange={(e) => setFetchKey(e.target.value)}
                        placeholder={`${fetchProvider} API key`}
                      />
                      <button className="setup-key-toggle" onClick={() => setShowFetchKey(!showFetchKey)} type="button">
                        {showFetchKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>Back</button>
              <button className="setup-btn setup-btn--primary" onClick={goNext}>
                Next <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Compute ── */}
        {step === "compute" && (
          <div className="setup-step">
            <div className="setup-step-header">
              <Server size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">Compute environments</h2>
                <p className="setup-subtitle">
                  OpenAgent uses sandboxed environments to run code safely. Both are optional.
                </p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-form">
              {/* E2B for Chat mode */}
              <div className="setup-compute-card">
                <div className="setup-compute-header">
                  <Server size={16} />
                  <div className="setup-compute-info">
                    <span className="setup-compute-name">E2B Sandbox</span>
                    <span className="setup-compute-badge">Chat mode</span>
                  </div>
                </div>
                <p className="setup-compute-desc">
                  Cloud sandbox for safe code execution. Get a free key at <a href="https://e2b.dev" target="_blank" rel="noreferrer">e2b.dev</a>
                </p>
                <div className="setup-field">
                  <label className="setup-label">API Key</label>
                  <div className="setup-key-wrap">
                    <input
                      className="setup-input setup-input--key"
                      type={showE2bKey ? "text" : "password"}
                      value={e2bKey}
                      onChange={(e) => setE2bKey(e.target.value)}
                      placeholder="e2b_..."
                    />
                    <button className="setup-key-toggle" onClick={() => setShowE2bKey(!showE2bKey)} type="button">
                      {showE2bKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Lima for Cowork mode */}
              <div className="setup-compute-card">
                <div className="setup-compute-header">
                  <Monitor size={16} />
                  <div className="setup-compute-info">
                    <span className="setup-compute-name">Lima VM</span>
                    <span className="setup-compute-badge">Cowork mode</span>
                  </div>
                </div>
                <p className="setup-compute-desc">
                  Local Linux VM for cowork sessions. Requires <a href="https://lima-vm.io" target="_blank" rel="noreferrer">Lima</a> to be installed on your machine.
                  Setup can be done later via the CLI.
                </p>
                <div className="setup-compute-status">
                  <span className="setup-compute-status-dot" />
                  Configured separately — no action needed here
                </div>
              </div>
            </div>

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>Back</button>
              <button className="setup-btn setup-btn--primary" onClick={goNext}>
                Next <ArrowRight size={14} />
              </button>
            </div>
          </div>
        )}

        {/* ── Step 5: Done ── */}
        {step === "done" && (
          <div className="setup-step">
            <div className="setup-done-icon">
              <Check size={32} strokeWidth={2.5} />
            </div>
            <h2 className="setup-title setup-title--center">You&rsquo;re all set!</h2>
            <p className="setup-subtitle setup-subtitle--center">
              Here&rsquo;s what you configured:
            </p>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-summary">
              <div className="setup-summary-row">
                <Sparkles size={14} />
                <span className="setup-summary-label">AI Model</span>
                <span className="setup-summary-value">
                  {displayName || autoDisplayName(modelId) || modelId}
                </span>
              </div>
              <div className="setup-summary-row">
                <ScrollText size={14} />
                <span className="setup-summary-label">Summarizer</span>
                <span className="setup-summary-value">
                  {sumSameAsMain
                    ? "Same as main"
                    : (sumDisplayName || autoDisplayName(sumModelId) || "Not configured")}
                </span>
              </div>
              <div className="setup-summary-row">
                <Globe size={14} />
                <span className="setup-summary-label">Web Search</span>
                <span className="setup-summary-value">
                  {searchProvider ? searchProvider.charAt(0).toUpperCase() + searchProvider.slice(1) : "Skipped"}
                </span>
              </div>
              <div className="setup-summary-row">
                <ScrollText size={14} />
                <span className="setup-summary-label">Web Fetch</span>
                <span className="setup-summary-value">
                  {fetchProvider ? fetchProvider.charAt(0).toUpperCase() + fetchProvider.slice(1) : "Skipped"}
                </span>
              </div>
              <div className="setup-summary-row">
                <Server size={14} />
                <span className="setup-summary-label">E2B Sandbox</span>
                <span className="setup-summary-value">
                  {e2bKey ? "Configured" : "Skipped"}
                </span>
              </div>
            </div>

            <p className="setup-footer">
              You can change any of these later in Settings.
            </p>

            <div className="setup-actions setup-actions--center">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>Back</button>
              <button
                className="setup-btn setup-btn--primary setup-btn--finish"
                onClick={handleFinish}
                disabled={saving}
              >
                {saving ? "Saving..." : "Start using OpenAgent"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
