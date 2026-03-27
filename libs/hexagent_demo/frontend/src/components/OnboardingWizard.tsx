import { useState, useEffect, useRef } from "react";
import faviconSvg from "../assets/favicon.svg";
import {
  Eye, EyeOff, ArrowRight, ChevronDown, ChevronRight,
  Sparkles, Globe, ScrollText, Server, Monitor, Check,
  CircleCheck, CircleAlert, Loader2, Sun, Moon,
} from "lucide-react";
import { getServerConfig, updateServerConfig } from "../api";
import type { ServerConfig, ModelConfig } from "../api";
import type { Settings } from "../hooks/useSettings";
import { useAppContext } from "../store";
import { useVMSetup } from "../vmSetup";

interface OnboardingWizardProps {
  open: boolean;
  onComplete: () => void;
  settings: Settings;
  onSettingsChange: (s: Settings | ((prev: Settings) => Settings)) => void;
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

type Step = "welcome" | "provider" | "model" | "summarizer" | "tools" | "compute" | "done";

const STEPS: Step[] = ["welcome", "provider", "model", "summarizer", "tools", "compute", "done"];

function stepIndex(s: Step): number {
  return STEPS.indexOf(s);
}

const ONBOARDING_DRAFT_KEY = "hexagent-onboarding-draft-v1";

interface OnboardingDraft {
  step?: Step;
  selectedProviderId?: string;
  modelId?: string;
  displayName?: string;
  baseUrl?: string;
  sumProviderId?: string;
  sumModelId?: string;
  sumDisplayName?: string;
  sumBaseUrl?: string;
  sumSameAsMain?: boolean;
  searchProvider?: string;
  fetchProvider?: string;
  vmSkipped?: boolean;
}

function loadOnboardingDraft(): OnboardingDraft | null {
  try {
    const raw = localStorage.getItem(ONBOARDING_DRAFT_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as OnboardingDraft;
  } catch {
    return null;
  }
}

function saveOnboardingDraft(draft: OnboardingDraft): void {
  localStorage.setItem(ONBOARDING_DRAFT_KEY, JSON.stringify(draft));
}

function clearOnboardingDraft(): void {
  localStorage.removeItem(ONBOARDING_DRAFT_KEY);
}

// ---------------------------------------------------------------------------

export default function OnboardingWizard({ open, onComplete, settings, onSettingsChange }: OnboardingWizardProps) {
  const { dispatch } = useAppContext();
  const draftReadyRef = useRef(false);
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

  // VM setup — shared with Settings via VMSetupProvider (single source of truth)
  const vm = useVMSetup();
  const vmAutoBootstrapping = vm.autoBootstrapping;
  const [vmSkipped, setVmSkipped] = useState(false);
  const [showSkipConfirm, setShowSkipConfirm] = useState(false);
  const [showDepsPrompt, setShowDepsPrompt] = useState(false);

  const vmSupported = vm.vmStatus === null ? null : vm.vmStatus.supported;
  const vmPhase1 = vm.phase1;
  const vmPhase1Msg = vm.phase1Msg;
  const vmPhase1Error = vm.phase1Error;
  const vmPhase2 = vm.phase2;
  const vmPhase2Msg = vm.phase2Msg;
  const vmPhase2Error = vm.phase2Error;
  const vmPhase3 = vm.phase3;
  const vmUsable = vmPhase1 === "done" && vmPhase2 === "done";
  const vmPhase1NeedsRestart = /restart windows|restart your computer|reboot/i.test(vmPhase1Error || "");

  // Load server config and restore onboarding draft on open
  useEffect(() => {
    if (!open) {
      draftReadyRef.current = false;
      return;
    }

    getServerConfig().then(setConfig).catch(() => {});

    const draft = loadOnboardingDraft();
    if (draft) {
      if (draft.step && STEPS.includes(draft.step)) setStep(draft.step);
      if (draft.selectedProviderId) setSelectedProvider(PROVIDERS.find((p) => p.id === draft.selectedProviderId) ?? null);
      if (typeof draft.modelId === "string") setModelId(draft.modelId);
      if (typeof draft.displayName === "string") setDisplayName(draft.displayName);
      if (typeof draft.baseUrl === "string") setBaseUrl(draft.baseUrl);
      if (draft.sumProviderId) setSumProvider(PROVIDERS.find((p) => p.id === draft.sumProviderId) ?? null);
      if (typeof draft.sumModelId === "string") setSumModelId(draft.sumModelId);
      if (typeof draft.sumDisplayName === "string") setSumDisplayName(draft.sumDisplayName);
      if (typeof draft.sumBaseUrl === "string") setSumBaseUrl(draft.sumBaseUrl);
      if (typeof draft.sumSameAsMain === "boolean") setSumSameAsMain(draft.sumSameAsMain);
      if (typeof draft.searchProvider === "string") setSearchProvider(draft.searchProvider);
      if (typeof draft.fetchProvider === "string") setFetchProvider(draft.fetchProvider);
      if (typeof draft.vmSkipped === "boolean") setVmSkipped(draft.vmSkipped);
    }

    draftReadyRef.current = true;
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open || !draftReadyRef.current) return;
    saveOnboardingDraft({
      step,
      selectedProviderId: selectedProvider?.id,
      modelId,
      displayName,
      baseUrl,
      sumProviderId: sumProvider?.id,
      sumModelId,
      sumDisplayName,
      sumBaseUrl,
      sumSameAsMain,
      searchProvider,
      fetchProvider,
      vmSkipped,
    });
  }, [
    open,
    step,
    selectedProvider,
    modelId,
    displayName,
    baseUrl,
    sumProvider,
    sumModelId,
    sumDisplayName,
    sumBaseUrl,
    sumSameAsMain,
    searchProvider,
    fetchProvider,
    vmSkipped,
  ]);

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
          e2b_api_key: "",
          chat_enabled: false,
        },
      };

      const saved = await updateServerConfig(updated);
      dispatch({ type: "SET_SERVER_CONFIG", payload: saved });
      clearOnboardingDraft();
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

        {/* ── Step 0: Welcome — Name & Theme ── */}
        {step === "welcome" && (
          <div className="setup-step setup-welcome">
            <div className="setup-welcome-brand">
              <img className="setup-welcome-logo" width="40" height="40" src={faviconSvg} alt="" />
              <h2 className="setup-welcome-title">ClawWork</h2>
            </div>
            <p className="setup-welcome-tagline">Powered by ClawWork harness</p>

            <div className="setup-welcome-form">
              <div className="setup-field">
                <label className="setup-label">What should ClawWork call you?</label>
                <input
                  className="setup-input setup-welcome-input"
                  type="text"
                  value={settings.fullName}
                  onChange={(e) => onSettingsChange((prev) => ({ ...prev, fullName: e.target.value }))}
                  placeholder="Your name"
                  autoComplete="off"
                  autoFocus
                />
              </div>

              <div className="setup-field">
                <label className="setup-label">Theme</label>
                <div className="setup-theme-options">
                  {(["light", "dark", "system"] as const).map((theme) => (
                    <button
                      key={theme}
                      className={`setup-theme-btn ${settings.theme === theme ? "setup-theme-btn--active" : ""}`}
                      type="button"
                      onClick={() => onSettingsChange((prev) => ({ ...prev, theme }))}
                    >
                      {theme === "light" && <Sun size={14} />}
                      {theme === "dark" && <Moon size={14} />}
                      {theme === "system" && <Monitor size={14} />}
                      <span>{theme.charAt(0).toUpperCase() + theme.slice(1)}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button className="setup-btn setup-btn--primary setup-welcome-cta" onClick={goNext}>
              Get Started <ArrowRight size={14} />
            </button>
          </div>
        )}

        {/* ── Step 1: Provider selection ── */}
        {step === "provider" && (
          <div className="setup-step">
            <div className="setup-step-header">
              <Sparkles size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">AI Model</h2>
                <p className="setup-subtitle">Choose your AI provider to get started</p>
              </div>
            </div>

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

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>Back</button>
            </div>
          </div>
        )}

        {/* ── Step 2: Model credentials ── */}
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
                    {showKey ? <Eye size={14} /> : <EyeOff size={14} />}
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
              <button className="setup-btn setup-btn--ghost" onClick={() => setStep("provider")}>Back</button>
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
                          {showSumKey ? <Eye size={14} /> : <EyeOff size={14} />}
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
                        {showSearchKey ? <Eye size={14} /> : <EyeOff size={14} />}
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
                        {showFetchKey ? <Eye size={14} /> : <EyeOff size={14} />}
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
                  ClawWork uses sandboxed environments to run code safely.
                </p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-form">
              {/* VM for Cowork mode */}
              <div className="setup-compute-card">
                <div className="setup-compute-header">
                  <Monitor size={16} />
                  <div className="setup-compute-info">
                    <span className="setup-compute-name">Virtual Machine</span>
                    <span className="setup-compute-badge">Required</span>
                  </div>
                </div>
                <p className="setup-compute-desc">
                  Local Linux VM for cowork sessions. You can skip this and set it up later in Settings.
                </p>

                {vmSupported === false && (
                  <div className="setup-compute-status">
                    <span className="setup-compute-status-dot" />
                    Not supported on this platform
                  </div>
                )}

                {vmSupported && !vmSkipped && (
                  <div className="setup-vm-phases">
                    {/* Phase 1: VM Engine */}
                    <div className="setup-vm-row">
                      {vmPhase1 === "done" ? <CircleCheck size={13} className="setup-vm-icon--done" /> :
                       vmPhase1 === "running" ? <Loader2 size={13} className="spin" /> :
                       vmPhase1 === "error" ? <CircleAlert size={13} className="setup-vm-icon--error" /> :
                       <span className="setup-vm-dot" />}
                      <span className="setup-vm-label">VM Engine</span>
                      {vmPhase1 === "done" && <span className="setup-vm-badge">Installed</span>}
                      {vmPhase1 === "running" && vmPhase1Msg && <span className="setup-vm-msg">{vmPhase1Msg}</span>}
                      {vmPhase1 === "pending" && (
                        vmAutoBootstrapping ? (
                          <span className="setup-vm-msg">Auto installing...</span>
                        ) : (
                          <button className="vm-phase-action" type="button" onClick={vm.installLima}>Install</button>
                        )
                      )}
                      {vmPhase1 === "error" && (
                        vmPhase1NeedsRestart ? (
                          <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={vm.recheckVmEngine}>
                            I've restarted, Re-check
                          </button>
                        ) : (
                          <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={vm.installLima}>
                            Retry
                          </button>
                        )
                      )}
                    </div>
                    {vmPhase1 === "error" && vmPhase1Error && (
                      <p className="setup-vm-error"><CircleAlert size={11} /> {vmPhase1Error}</p>
                    )}

                    {/* Phase 2: VM Instance */}
                    <div className="setup-vm-row">
                      {vmPhase2 === "done" ? <CircleCheck size={13} className="setup-vm-icon--done" /> :
                       vmPhase2 === "running" ? <Loader2 size={13} className="spin" /> :
                       vmPhase2 === "error" ? <CircleAlert size={13} className="setup-vm-icon--error" /> :
                       <span className="setup-vm-dot" />}
                      <span className="setup-vm-label">VM Instance</span>
                      {vmPhase2 === "done" && <span className="setup-vm-badge">Ready</span>}
                      {vmPhase2 === "running" && vmPhase2Msg && <span className="setup-vm-msg">{vmPhase2Msg}</span>}
                      {vmPhase2 === "pending" && vmPhase1 === "done" && (
                        vmAutoBootstrapping ? (
                          <span className="setup-vm-msg">Auto installing...</span>
                        ) : (
                          <button className="vm-phase-action" type="button" onClick={vm.buildVMInstance}>Install</button>
                        )
                      )}
                      {vmPhase2 === "error" && (
                        <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={vm.buildVMInstance}>Retry</button>
                      )}
                    </div>
                    {vmPhase2 === "error" && vmPhase2Error && (
                      <p className="setup-vm-error"><CircleAlert size={11} /> {vmPhase2Error}</p>
                    )}

                    {/* Phase 3: System Dependencies */}
                    <div className="setup-vm-row">
                      {vmPhase3 === "done" ? <CircleCheck size={13} className="setup-vm-icon--done" /> :
                       vmPhase3 === "running" ? <Loader2 size={13} className="spin" /> :
                       vmPhase3 === "error" ? <CircleAlert size={13} className="setup-vm-icon--error" /> :
                       <span className="setup-vm-dot" />}
                      <span className="setup-vm-label">VM System Dependencies</span>
                      {vmPhase3 === "done" && <span className="setup-vm-badge">Complete</span>}
                      {vmPhase3 === "running" && <span className="setup-vm-msg">Installing...</span>}
                      {vmPhase3 === "pending" && vmUsable && (
                        <button className="vm-phase-action" type="button" onClick={() => vm.startProvision()}>Install in background</button>
                      )}
                      {vmPhase3 === "error" && (
                        <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={() => vm.startProvision()}>Retry</button>
                      )}
                    </div>

                    {vmUsable && vmPhase3 !== "done" && (
                      <p className="setup-vm-hint">
                        System dependencies install in the background — you can continue using ClawWork while it runs.
                      </p>
                    )}
                  </div>
                )}

                {vmSupported && vmSkipped && (
                  <>
                    <div className="setup-compute-status">
                      <span className="setup-compute-status-dot" />
                      Skipped — you can set this up later in Settings
                    </div>
                    <button
                      className="setup-btn--link"
                      type="button"
                      onClick={() => { setVmSkipped(false); setShowSkipConfirm(false); }}
                    >
                      Set up Cowork
                    </button>
                  </>
                )}
              </div>

            </div>

            {/* Skip confirmation popup */}
            {showSkipConfirm && (
              <div className="setup-skip-overlay" onClick={() => setShowSkipConfirm(false)}>
                <div className="setup-skip-popup" onClick={(e) => e.stopPropagation()}>
                  <p className="setup-skip-title">Are you sure you want to skip?</p>
                  <ul className="setup-skip-list">
                    {vmSupported && !vmUsable && !vmSkipped && (
                      <li>Without a <strong>Virtual Machine</strong>, Cowork mode will not be available.</li>
                    )}
                    {vmUsable && vmPhase3 !== "done" && vmPhase3 !== "running" && (
                      <li><strong>VM System Dependencies</strong> are not installed. Cowork mode will work but the agent may lack some tools. You can install them later in Settings (runs in the background).</li>
                    )}
                  </ul>
                  <p className="setup-skip-note">You can configure these later in Settings.</p>
                  <div className="setup-skip-actions">
                    <button
                      className="setup-btn setup-btn--ghost"
                      type="button"
                      onClick={() => setShowSkipConfirm(false)}
                    >
                      Go back
                    </button>
                    <button
                      className="setup-btn setup-btn--danger"
                      type="button"
                      onClick={() => {
                        if (!vmUsable && vmSupported) setVmSkipped(true);
                        setShowSkipConfirm(false);
                        goNext();
                      }}
                    >
                      Skip anyway
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Deps recommendation popup */}
            {showDepsPrompt && (
              <div className="setup-skip-overlay" onClick={() => setShowDepsPrompt(false)}>
                <div className="setup-skip-popup" onClick={(e) => e.stopPropagation()}>
                  <p className="setup-skip-title setup-skip-title--recommend">Install system dependencies?</p>
                  <p className="setup-deps-desc">
                    Installing VM system dependencies is <strong>strongly recommended</strong>. It gives the agent access
                    to tools like Python, Node.js, LaTeX, LibreOffice, and more.
                  </p>
                  <p className="setup-deps-desc">
                    The installation runs in the background — you can start using ClawWork immediately.
                  </p>
                  <div className="setup-skip-actions">
                    <button
                      className="setup-btn setup-btn--ghost"
                      type="button"
                      onClick={() => { setShowDepsPrompt(false); goNext(); }}
                    >
                      Continue without
                    </button>
                    <button
                      className="setup-btn setup-btn--primary"
                      type="button"
                      onClick={() => { vm.startProvision(); setShowDepsPrompt(false); goNext(); }}
                    >
                      Install & Continue
                    </button>
                  </div>
                </div>
              </div>
            )}

            {(() => {
              const vmReady = vmUsable || vmSkipped || vmSupported === false;
              const canProceed = vmReady;
              const anyVmRunning = vmPhase1 === "running" || vmPhase2 === "running" || vmPhase3 === "running";
              const needsDepsPrompt = canProceed && vmUsable && vmPhase3 !== "done" && vmPhase3 !== "running";
              const handleNext = () => {
                if (needsDepsPrompt) { setShowDepsPrompt(true); return; }
                goNext();
              };
              return (
                <div className="setup-actions">
                  <button className="setup-btn setup-btn--ghost" onClick={goBack}>Back</button>
                  <div className="setup-actions-right">
                    {!canProceed && !showSkipConfirm && (
                      <button
                        className="setup-btn setup-btn--skip"
                        type="button"
                        onClick={() => setShowSkipConfirm(true)}
                      >
                        Skip
                      </button>
                    )}
                    <button
                      className="setup-btn setup-btn--primary"
                      onClick={handleNext}
                      disabled={!canProceed || anyVmRunning}
                    >
                      Next <ArrowRight size={14} />
                    </button>
                  </div>
                </div>
              );
            })()}
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
                <Monitor size={14} />
                <span className="setup-summary-label">Virtual Machine</span>
                <span className="setup-summary-value">
                  {vmSkipped ? "Skipped" : vmUsable ? "Ready" : "Not set up"}
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
                {saving ? "Saving..." : "Start using ClawWork"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
