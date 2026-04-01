/**
 * Auth API — captcha, SMS code, and login endpoints.
 * Base path: /app (as per the login specification).
 */

const AUTH_BASE = "https://maas.ai-yuanjing.com/app";

export interface CaptchaResponse {
  code: number;
  data: { captchaId: string; b64s: string };
  msg: string;
}

export interface SendCodeResponse {
  code: number;
  msg: string;
}

export interface LoginResponse {
  code: number;
  data: {
    token: string;
    expires_in: number;
    scope: string;
    [key: string]: unknown;
  };
  msg: string;
}

export async function getCaptcha(): Promise<CaptchaResponse> {
  const res = await fetch(`${AUTH_BASE}/login/captcha`);
  if (!res.ok) throw new Error(`Failed to get captcha: ${res.statusText}`);
  return res.json();
}

export async function sendSmsCode(phone: string, captchaCode: string, captchaId: string): Promise<SendCodeResponse> {
  const res = await fetch(`${AUTH_BASE}/login/sendCode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, captchaCode, captchaId }),
  });
  if (!res.ok) throw new Error(`Failed to send code: ${res.statusText}`);
  return res.json();
}

export async function smsLogin(phone: string, smsCode: string): Promise<LoginResponse> {
  const res = await fetch(`${AUTH_BASE}/login/smsLogin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, smsCode, application: "uniclaw" }),
  });
  if (!res.ok) throw new Error(`Failed to login: ${res.statusText}`);
  return res.json();
}
