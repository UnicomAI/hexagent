import { useState, useEffect } from "react";
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
import { useTranslation } from "../i18n";

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

// ---------------------------------------------------------------------------

export default function OnboardingWizard({ open, onComplete, settings, onSettingsChange }: OnboardingWizardProps) {
  const { dispatch } = useAppContext();
  const { t } = useTranslation();
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

  // VM setup — shared with Settings via VMSetupProvider (single source of truth)
  const vm = useVMSetup();
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

  // Load server config and reset name on open
  useEffect(() => {
    if (open) {
      getServerConfig().then(setConfig).catch(() => {});
      onSettingsChange((prev) => ({ ...prev, fullName: "" }));
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

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
      setError(t("onboarding.configureFirst"));
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
      setError(e instanceof Error ? e.message : t("onboarding.saveFailed"));
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
              <h2 className="setup-welcome-title">HexAgent</h2>
            </div>
            <p className="setup-welcome-tagline">{t("onboarding.poweredBy")}</p>

            <div className="setup-welcome-form">
              <div className="setup-field">
                <label className="setup-label">{t("onboarding.whatToCall")}</label>
                <input
                  className="setup-input setup-welcome-input"
                  type="text"
                  value={settings.fullName}
                  onChange={(e) => onSettingsChange((prev) => ({ ...prev, fullName: e.target.value }))}
                  placeholder={t("settings.general.fullNamePlaceholder")}
                  autoComplete="off"
                  autoFocus
                />
              </div>

              <div className="setup-field">
                <label className="setup-label">{t("onboarding.theme")}</label>
                <div className="setup-theme-options">
                  {(["light", "dark", "system"] as const).map((theme) => {
                    const themeLabels = { light: t("settings.general.light"), dark: t("settings.general.dark"), system: t("settings.general.system") };
                    return (
                      <button
                        key={theme}
                        className={`setup-theme-btn ${settings.theme === theme ? "setup-theme-btn--active" : ""}`}
                        type="button"
                        onClick={() => onSettingsChange((prev) => ({ ...prev, theme }))}
                      >
                        {theme === "light" && <Sun size={14} />}
                        {theme === "dark" && <Moon size={14} />}
                        {theme === "system" && <Monitor size={14} />}
                        <span>{themeLabels[theme]}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            <button className="setup-btn setup-btn--primary setup-welcome-cta" onClick={goNext}>
              {t("onboarding.getStarted")} <ArrowRight size={14} />
            </button>
          </div>
        )}

        {/* ── Step 1: Provider selection ── */}
        {step === "provider" && (
          <div className="setup-step">
            <div className="setup-step-header">
              <Sparkles size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">{t("onboarding.aiModel")}</h2>
                <p className="setup-subtitle">{t("onboarding.chooseProvider")}</p>
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
              {t("onboarding.addMoreLater")}
            </p>

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>{t("common.back")}</button>
            </div>
          </div>
        )}

        {/* ── Step 2: Model credentials ── */}
        {step === "model" && selectedProvider && (
          <div className="setup-step">
            <div className="setup-step-header">
              <Sparkles size={20} className="setup-step-icon" />
              <div>
                <h2 className="setup-title">{t("onboarding.configure", { provider: selectedProvider.label })}</h2>
                <p className="setup-subtitle">{t("onboarding.enterCredentials")}</p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-form">
              <div className="setup-field">
                <label className="setup-label">{t("common.apiKey")}</label>
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
                <label className="setup-label">{t("common.modelId")}</label>
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
                    <label className="setup-label">{t("common.baseUrl")}</label>
                    <input
                      className="setup-input"
                      value={baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                      placeholder="https://api.example.com/v1"
                    />
                  </div>
                  <div className="setup-field">
                    <label className="setup-label">{t("common.displayName")}</label>
                    <input
                      className="setup-input"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      placeholder={autoDisplayName(modelId) || t("settings.model.myModel")}
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
                    {t("common.advanced")}
                  </button>

                  {showAdvanced && (
                    <div className="setup-advanced">
                      <div className="setup-field">
                        <label className="setup-label">{t("common.baseUrl")}</label>
                        <input
                          className="setup-input"
                          value={baseUrl}
                          onChange={(e) => setBaseUrl(e.target.value)}
                          placeholder={selectedProvider.base_url}
                        />
                      </div>
                      <div className="setup-field">
                        <label className="setup-label">{t("common.displayName")}</label>
                        <input
                          className="setup-input"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          placeholder={autoDisplayName(modelId) || t("settings.model.myModel")}
                        />
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="setup-actions">
              <button className="setup-btn setup-btn--ghost" onClick={() => setStep("provider")}>{t("common.back")}</button>
              <button
                className="setup-btn setup-btn--primary"
                onClick={goNext}
                disabled={!canProceedFromModel}
              >
                {t("common.next")} <ArrowRight size={14} />
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
                <h2 className="setup-title">{t("onboarding.summarizer")}</h2>
                <p className="setup-subtitle">
                  {t("onboarding.summarizerDesc")}
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
                  {t("onboarding.sameAsMain")}
                </button>
                <button
                  className={`setup-pill ${!sumSameAsMain ? "setup-pill--active" : ""}`}
                  onClick={() => setSumSameAsMain(false)}
                  type="button"
                >
                  {t("onboarding.differentModel")}
                </button>
              </div>
            </div>

            {!sumSameAsMain && (
              <div className="setup-form">
                <div className="setup-field">
                  <label className="setup-label">{t("common.provider")}</label>
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
                      <label className="setup-label">{t("common.apiKey")}</label>
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
                      <label className="setup-label">{t("common.modelId")}</label>
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
                          <label className="setup-label">{t("common.baseUrl")}</label>
                          <input
                            className="setup-input"
                            value={sumBaseUrl}
                            onChange={(e) => setSumBaseUrl(e.target.value)}
                            placeholder="https://api.example.com/v1"
                          />
                        </div>
                        <div className="setup-field">
                          <label className="setup-label">{t("common.displayName")}</label>
                          <input
                            className="setup-input"
                            value={sumDisplayName}
                            onChange={(e) => setSumDisplayName(e.target.value)}
                            placeholder={autoDisplayName(sumModelId) || t("onboarding.fastModel")}
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
                          {t("common.advanced")}
                        </button>

                        {sumShowAdvanced && (
                          <div className="setup-advanced">
                            <div className="setup-field">
                              <label className="setup-label">{t("common.baseUrl")}</label>
                              <input
                                className="setup-input"
                                value={sumBaseUrl}
                                onChange={(e) => setSumBaseUrl(e.target.value)}
                                placeholder={sumProvider.base_url}
                              />
                            </div>
                            <div className="setup-field">
                              <label className="setup-label">{t("common.displayName")}</label>
                              <input
                                className="setup-input"
                                value={sumDisplayName}
                                onChange={(e) => setSumDisplayName(e.target.value)}
                                placeholder={autoDisplayName(sumModelId) || t("onboarding.fastModel")}
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
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>{t("common.back")}</button>
              <button className="setup-btn setup-btn--primary" onClick={goNext}>
                {t("common.next")} <ArrowRight size={14} />
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
                <h2 className="setup-title">{t("onboarding.webTools")}</h2>
                <p className="setup-subtitle">
                  {t("onboarding.webToolsDesc")}
                </p>
              </div>
            </div>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-form">
              {/* Web Search */}
              <div className="setup-tool-group">
                <div className="setup-tool-header">
                  <Globe size={14} />
                  <span>{t("onboarding.webSearch")}</span>
                </div>
                <div className="setup-field">
                  <label className="setup-label">{t("common.provider")}</label>
                  <div className="setup-pill-group">
                    {[
                      { id: "", label: t("common.none") },
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
                    <label className="setup-label">{t("common.apiKey")}</label>
                    <div className="setup-key-wrap">
                      <input
                        className="setup-input setup-input--key"
                        type={showSearchKey ? "text" : "password"}
                        value={searchKey}
                        onChange={(e) => setSearchKey(e.target.value)}
                        placeholder={t("onboarding.searchApiKeyPlaceholder", { provider: searchProvider })}
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
                  <span>{t("onboarding.webFetch")}</span>
                </div>
                <div className="setup-field">
                  <label className="setup-label">{t("common.provider")}</label>
                  <div className="setup-pill-group">
                    {[
                      { id: "", label: t("common.none") },
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
                    <label className="setup-label">{t("common.apiKey")}</label>
                    <div className="setup-key-wrap">
                      <input
                        className="setup-input setup-input--key"
                        type={showFetchKey ? "text" : "password"}
                        value={fetchKey}
                        onChange={(e) => setFetchKey(e.target.value)}
                        placeholder={t("onboarding.fetchApiKeyPlaceholder", { provider: fetchProvider })}
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
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>{t("common.back")}</button>
              <button className="setup-btn setup-btn--primary" onClick={goNext}>
                {t("common.next")} <ArrowRight size={14} />
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
                <h2 className="setup-title">{t("onboarding.compute")}</h2>
                <p className="setup-subtitle">
                  {t("onboarding.computeDesc")}
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
                    <span className="setup-compute-name">{t("onboarding.e2bSandbox")}</span>
                    <span className="setup-compute-badge">{t("onboarding.e2bBadge")}</span>
                  </div>
                </div>
                <p className="setup-compute-desc">
                  {t("onboarding.e2bDesc")} Get a free key at <a href="https://e2b.dev" target="_blank" rel="noreferrer">e2b.dev</a>
                </p>
                <div className="setup-field">
                  <label className="setup-label">{t("common.apiKey")}</label>
                  <div className="setup-key-wrap">
                    <input
                      className="setup-input setup-input--key"
                      type={showE2bKey ? "text" : "password"}
                      value={e2bKey}
                      onChange={(e) => setE2bKey(e.target.value)}
                      placeholder="e2b_..."
                    />
                    <button className="setup-key-toggle" onClick={() => setShowE2bKey(!showE2bKey)} type="button">
                      {showE2bKey ? <Eye size={14} /> : <EyeOff size={14} />}
                    </button>
                  </div>
                </div>
              </div>

              {/* VM for Cowork mode */}
              <div className="setup-compute-card">
                <div className="setup-compute-header">
                  <Monitor size={16} />
                  <div className="setup-compute-info">
                    <span className="setup-compute-name">{t("onboarding.vmTitle")}</span>
                    <span className="setup-compute-badge">{t("onboarding.vmBadge")}</span>
                  </div>
                </div>
                <p className="setup-compute-desc">
                  {t("onboarding.vmDesc")}
                </p>

                {vmSupported === false && (
                  <div className="setup-compute-status">
                    <span className="setup-compute-status-dot" />
                    {t("onboarding.vmNotSupported")}
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
                      <span className="setup-vm-label">{t("onboarding.vmEngine")}</span>
                      {vmPhase1 === "done" && <span className="setup-vm-badge">{t("onboarding.vmInstalled")}</span>}
                      {vmPhase1 === "running" && vmPhase1Msg && <span className="setup-vm-msg">{vmPhase1Msg}</span>}
                      {vmPhase1 === "pending" && (
                        <button className="vm-phase-action" type="button" onClick={vm.installLima}>{t("common.install")}</button>
                      )}
                      {vmPhase1 === "error" && (
                        <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={vm.installLima}>{t("common.retry")}</button>
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
                      <span className="setup-vm-label">{t("onboarding.vmInstance")}</span>
                      {vmPhase2 === "done" && <span className="setup-vm-badge">{t("onboarding.vmReady")}</span>}
                      {vmPhase2 === "running" && vmPhase2Msg && <span className="setup-vm-msg">{vmPhase2Msg}</span>}
                      {vmPhase2 === "pending" && vmPhase1 === "done" && (
                        <button className="vm-phase-action" type="button" onClick={vm.buildVMInstance}>{t("common.install")}</button>
                      )}
                      {vmPhase2 === "error" && (
                        <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={vm.buildVMInstance}>{t("common.retry")}</button>
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
                      <span className="setup-vm-label">{t("onboarding.vmDeps")}</span>
                      {vmPhase3 === "done" && <span className="setup-vm-badge">{t("onboarding.vmComplete")}</span>}
                      {vmPhase3 === "running" && <span className="setup-vm-msg">{t("onboarding.vmInstalling")}</span>}
                      {vmPhase3 === "pending" && vmUsable && (
                        <button className="vm-phase-action" type="button" onClick={() => vm.startProvision()}>{t("onboarding.installInBackground")}</button>
                      )}
                      {vmPhase3 === "error" && (
                        <button className="vm-phase-action vm-phase-action--retry" type="button" onClick={() => vm.startProvision()}>{t("common.retry")}</button>
                      )}
                    </div>

                    {vmUsable && vmPhase3 !== "done" && (
                      <p className="setup-vm-hint">
                        {t("onboarding.vmDepsHint")}
                      </p>
                    )}
                  </div>
                )}

                {vmSupported && vmSkipped && (
                  <>
                    <div className="setup-compute-status">
                      <span className="setup-compute-status-dot" />
                      {t("onboarding.vmSkipped")}
                    </div>
                    <button
                      className="setup-btn--link"
                      type="button"
                      onClick={() => { setVmSkipped(false); setShowSkipConfirm(false); }}
                    >
                      {t("onboarding.setupCowork")}
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Skip confirmation popup */}
            {showSkipConfirm && (
              <div className="setup-skip-overlay" onClick={() => setShowSkipConfirm(false)}>
                <div className="setup-skip-popup" onClick={(e) => e.stopPropagation()}>
                  <p className="setup-skip-title">{t("onboarding.skipConfirmTitle")}</p>
                  <ul className="setup-skip-list">
                    {!e2bKey.trim() && (
                      <li dangerouslySetInnerHTML={{ __html: t("onboarding.skipNoE2b") }} />
                    )}
                    {vmSupported && !vmUsable && !vmSkipped && (
                      <li dangerouslySetInnerHTML={{ __html: t("onboarding.skipNoVm") }} />
                    )}
                    {vmUsable && vmPhase3 !== "done" && vmPhase3 !== "running" && (
                      <li dangerouslySetInnerHTML={{ __html: t("onboarding.skipNoDeps") }} />
                    )}
                  </ul>
                  <p className="setup-skip-note">{t("onboarding.skipNote")}</p>
                  <div className="setup-skip-actions">
                    <button
                      className="setup-btn setup-btn--ghost"
                      type="button"
                      onClick={() => setShowSkipConfirm(false)}
                    >
                      {t("onboarding.goBack")}
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
                      {t("onboarding.skipAnyway")}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Deps recommendation popup */}
            {showDepsPrompt && (
              <div className="setup-skip-overlay" onClick={() => setShowDepsPrompt(false)}>
                <div className="setup-skip-popup" onClick={(e) => e.stopPropagation()}>
                  <p className="setup-skip-title setup-skip-title--recommend">{t("onboarding.depsPromptTitle")}</p>
                  <p className="setup-deps-desc" dangerouslySetInnerHTML={{ __html: t("onboarding.depsDesc1") }} />
                  <p className="setup-deps-desc" dangerouslySetInnerHTML={{ __html: t("onboarding.depsDesc2") }} />
                  <div className="setup-skip-actions">
                    <button
                      className="setup-btn setup-btn--ghost"
                      type="button"
                      onClick={() => { setShowDepsPrompt(false); goNext(); }}
                    >
                      {t("onboarding.continueWithout")}
                    </button>
                    <button
                      className="setup-btn setup-btn--primary"
                      type="button"
                      onClick={() => { vm.startProvision(); setShowDepsPrompt(false); goNext(); }}
                    >
                      {t("onboarding.installAndContinue")}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {(() => {
              const hasE2b = !!e2bKey.trim();
              const vmReady = vmUsable || vmSkipped || vmSupported === false;
              const canProceed = hasE2b && vmReady;
              const anyVmRunning = vmPhase1 === "running" || vmPhase2 === "running" || vmPhase3 === "running";
              const needsDepsPrompt = canProceed && vmUsable && vmPhase3 !== "done" && vmPhase3 !== "running";
              const handleNext = () => {
                if (needsDepsPrompt) { setShowDepsPrompt(true); return; }
                goNext();
              };
              return (
                <div className="setup-actions">
                  <button className="setup-btn setup-btn--ghost" onClick={goBack}>{t("common.back")}</button>
                  <div className="setup-actions-right">
                    {!canProceed && !showSkipConfirm && (
                      <button
                        className="setup-btn setup-btn--skip"
                        type="button"
                        onClick={() => setShowSkipConfirm(true)}
                      >
                        {t("common.skip")}
                      </button>
                    )}
                    <button
                      className="setup-btn setup-btn--primary"
                      onClick={handleNext}
                      disabled={!canProceed || anyVmRunning}
                    >
                      {t("common.next")} <ArrowRight size={14} />
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
            <h2 className="setup-title setup-title--center">{t("onboarding.allSet")}</h2>
            <p className="setup-subtitle setup-subtitle--center">
              {t("onboarding.summary")}
            </p>

            {error && <div className="setup-error">{error}</div>}

            <div className="setup-summary">
              <div className="setup-summary-row">
                <Sparkles size={14} />
                <span className="setup-summary-label">{t("onboarding.summaryModel")}</span>
                <span className="setup-summary-value">
                  {displayName || autoDisplayName(modelId) || modelId}
                </span>
              </div>
              <div className="setup-summary-row">
                <ScrollText size={14} />
                <span className="setup-summary-label">{t("onboarding.summarySummarizer")}</span>
                <span className="setup-summary-value">
                  {sumSameAsMain
                    ? t("onboarding.sameAsMainShort")
                    : (sumDisplayName || autoDisplayName(sumModelId) || t("onboarding.notConfigured"))}
                </span>
              </div>
              <div className="setup-summary-row">
                <Globe size={14} />
                <span className="setup-summary-label">{t("onboarding.summarySearch")}</span>
                <span className="setup-summary-value">
                  {searchProvider ? searchProvider.charAt(0).toUpperCase() + searchProvider.slice(1) : t("common.skipped")}
                </span>
              </div>
              <div className="setup-summary-row">
                <ScrollText size={14} />
                <span className="setup-summary-label">{t("onboarding.summaryFetch")}</span>
                <span className="setup-summary-value">
                  {fetchProvider ? fetchProvider.charAt(0).toUpperCase() + fetchProvider.slice(1) : t("common.skipped")}
                </span>
              </div>
              <div className="setup-summary-row">
                <Server size={14} />
                <span className="setup-summary-label">{t("onboarding.summaryE2b")}</span>
                <span className="setup-summary-value">
                  {e2bKey ? t("common.configured") : t("common.skipped")}
                </span>
              </div>
              <div className="setup-summary-row">
                <Monitor size={14} />
                <span className="setup-summary-label">{t("onboarding.summaryVm")}</span>
                <span className="setup-summary-value">
                  {vmSkipped ? t("common.skipped") : vmUsable ? t("common.ready") : t("onboarding.notSetUp")}
                </span>
              </div>
            </div>

            <p className="setup-footer">
              {t("onboarding.changeLater")}
            </p>

            <div className="setup-actions setup-actions--center">
              <button className="setup-btn setup-btn--ghost" onClick={goBack}>{t("common.back")}</button>
              <button
                className="setup-btn setup-btn--primary setup-btn--finish"
                onClick={handleFinish}
                disabled={saving}
              >
                {saving ? t("onboarding.saving") : t("onboarding.startUsing")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
