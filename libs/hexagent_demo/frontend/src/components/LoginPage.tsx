import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import brandLogo from "../assets/brand-logo.png";
import { getCaptcha, sendSmsCode, smsLogin } from "../authApi";

interface LoginPageProps {
  onLoginSuccess: (token: string, userData: Record<string, unknown>, expiresIn: number, scope: string) => void;
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const { t } = useTranslation("login");

  const [phone, setPhone] = useState("");
  const [captchaCode, setCaptchaCode] = useState("");
  const [captchaId, setCaptchaId] = useState("");
  const [captchaImg, setCaptchaImg] = useState("");
  const [smsCode, setSmsCode] = useState("");
  const [countdown, setCountdown] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const phoneValid = /^1[3-9]\d{9}$/.test(phone);

  // Fetch captcha on mount
  const fetchCaptcha = useCallback(async () => {
    try {
      const res = await getCaptcha();
      if (res.code === 0) {
        setCaptchaId(res.data.captchaId);
        setCaptchaImg(res.data.b64s);
      }
    } catch {
      // silently retry on click
    }
  }, []);

  useEffect(() => {
    fetchCaptcha();
  }, [fetchCaptcha]);

  // Countdown timer
  useEffect(() => {
    if (countdown <= 0) {
      if (countdownRef.current) clearInterval(countdownRef.current);
      return;
    }
    countdownRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (countdownRef.current) clearInterval(countdownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
    };
  }, [countdown > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSendCode = async () => {
    if (!phoneValid || !captchaCode) return;
    setError("");
    try {
      const res = await sendSmsCode(phone, captchaCode, captchaId);
      if (res.code === 0) {
        setCountdown(60);
      } else if (res.code === 1002) {
        setCaptchaCode("");
        setError(res.msg || t("captchaError"));
      } else {
        setError(res.msg || t("sendCodeFailed"));
      }
    } catch {
      setError(t("sendCodeFailed"));
    }
  };

  const handleLogin = async () => {
    if (!phoneValid || !smsCode) return;
    setLoading(true);
    setError("");
    try {
      const res = await smsLogin(phone, smsCode);
      if (res.code === 0) {
        const { token, expires_in, scope, ...rest } = res.data;
        onLoginSuccess(token, { token, expires_in, scope, ...rest }, expires_in, scope);
      } else {
        if (res.msg === "验证码失效，请重新发送短信") {
          await fetchCaptcha();
          setCaptchaCode("");
          setSmsCode("");
        }
        setError(res.msg || t("loginFailed"));
      }
    } catch {
      setError(t("loginFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && phoneValid && smsCode && !loading) {
      handleLogin();
    }
  };

  return (
    <div className="login-container" onKeyDown={handleKeyDown}>
      <div className="login-card">
        {/* Header */}
        <div className="login-header">
          <img src={brandLogo} alt="Logo" className="login-logo" />
          <span className="login-app-name">{t("appName")}</span>
        </div>

        {/* Phone */}
        <div className="login-field">
          <div className="login-input-group">
            <span className="login-addon">+86</span>
            <input
              type="tel"
              className="login-input"
              placeholder={t("phonePlaceholder")}
              value={phone}
              onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 11))}
              maxLength={11}
            />
          </div>
        </div>

        {/* Captcha */}
        <div className="login-field">
          <div className="login-input-group">
            <input
              type="text"
              className="login-input login-input-captcha"
              placeholder={t("captchaPlaceholder")}
              value={captchaCode}
              onChange={(e) => setCaptchaCode(e.target.value)}
            />
            <div
              className="login-captcha-img"
              onClick={fetchCaptcha}
              title={t("refreshCaptcha")}
            >
              {captchaImg ? (
                <img src={captchaImg} alt="captcha" />
              ) : (
                <span className="login-captcha-loading">{t("loadingCaptcha")}</span>
              )}
            </div>
          </div>
        </div>

        {/* SMS Code */}
        <div className="login-field">
          <div className="login-input-group">
            <input
              type="text"
              className="login-input login-input-sms"
              placeholder={t("smsPlaceholder")}
              value={smsCode}
              onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              maxLength={6}
            />
            <button
              className="login-send-btn"
              onClick={handleSendCode}
              disabled={!phoneValid || !captchaCode || countdown > 0}
            >
              {countdown > 0 ? `${countdown}s${t("resendAfter")}` : t("sendCode")}
            </button>
          </div>
        </div>

        {/* Error */}
        {error && <div className="login-error">{error}</div>}

        {/* Login button */}
        <button
          className="login-btn"
          onClick={handleLogin}
          disabled={!phoneValid || !smsCode || loading}
        >
          {loading ? t("loggingIn") : t("login")}
        </button>
      </div>
    </div>
  );
}
