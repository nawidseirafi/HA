import {
  browserSupportsWebAuthn, startAuthentication, startRegistration,
  type PublicKeyCredentialCreationOptionsJSON, type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser';
import { request, type AuthResponse } from '@shared/api/client';

export type Passkey = {
  id: string;
  name: string;
  rp_id: string;
  created_at: number;
  last_used_at: number | null;
};

type Ceremony<T> = { challenge_id: string; options: T };

export function passkeySupportMessage(): string {
  if (!window.isSecureContext) return 'Face ID / Passkeys benötigen eine HTTPS-Verbindung. Bitte die sichere Adresse von RoboterSteve öffnen.';
  if (!browserSupportsWebAuthn()) return 'Dieser Browser unterstützt keine Passkeys. Bitte einen aktuellen Browser verwenden oder mit Passwort anmelden.';
  return '';
}

export function passkeyError(error: unknown): string {
  if (error instanceof Error) {
    if (error.name === 'NotAllowedError' || error.name === 'AbortError') {
      return 'Die Passkey-Anfrage wurde abgebrochen oder nicht bestätigt. Du kannst es erneut versuchen oder dein Passwort verwenden.';
    }
    if (error.name === 'InvalidStateError') return 'Auf diesem Gerät ist bereits ein Passkey für RoboterSteve eingerichtet.';
    if (error.name === 'SecurityError') return 'Die Passkey-Adresse passt nicht zur Website. Bitte die HTTPS-Adresse und die Serverkonfiguration prüfen.';
    return error.message;
  }
  return 'Der Passkey konnte nicht verwendet werden. Bitte erneut versuchen.';
}

export async function authenticateWithPasskey(): Promise<AuthResponse> {
  const ceremony = await request<Ceremony<PublicKeyCredentialRequestOptionsJSON>>('/api/auth/passkeys/login/options', { method: 'POST' });
  const credential = await startAuthentication({ optionsJSON: ceremony.options });
  return request<AuthResponse>('/api/auth/passkeys/login/verify', {
    method: 'POST', body: JSON.stringify({ challenge_id: ceremony.challenge_id, credential }),
  });
}

export async function registerPasskey(password: string, name: string): Promise<void> {
  const ceremony = await request<Ceremony<PublicKeyCredentialCreationOptionsJSON>>('/api/auth/passkeys/register/options', {
    method: 'POST', body: JSON.stringify({ password }),
  });
  const credential = await startRegistration({ optionsJSON: ceremony.options });
  await request('/api/auth/passkeys/register/verify', {
    method: 'POST', body: JSON.stringify({ challenge_id: ceremony.challenge_id, credential, name }),
  });
}

export const listPasskeys = () => request<{ passkeys: Passkey[] }>('/api/auth/passkeys');
export const removePasskey = (id: string) => request('/api/auth/passkeys/' + encodeURIComponent(id), { method: 'DELETE' });
