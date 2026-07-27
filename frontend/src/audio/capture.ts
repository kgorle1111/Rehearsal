// 10-frontend-spec.md §7.2-7.3 — the interface this module must expose once a real audio
// pipeline exists. STUBBED: no live getUserMedia/AudioWorklet capture is wired here.
//
// Why: the backend's AudioIO (WS4) is a Protocol with fakes only as of this build — there is
// no real host to send PCM frames to, and building a capture path against nothing would be a
// silently-broken "working" feature (the exact failure BUILD.md's WS8 scope note prohibits).
// This module defines the real contract from §7.2 so preflight-view and the level meter can be
// wired against it later with no interface change — only the implementation of startCapture()
// needs to change from "throw NotImplemented" to a real getUserMedia + AudioWorklet graph.

import { signal } from '../store/signal';
import type { Signal } from '../store/signal';

export interface CaptureHandle {
  readonly deviceId: string;
  readonly level: Signal<number>;
  readonly clipping: Signal<boolean>;
  stop(): void;
}

export async function listInputDevices(): Promise<MediaDeviceInfo[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === 'audioinput');
}

export async function permissionState(): Promise<PermissionState> {
  try {
    const status = await navigator.permissions.query({
      name: 'microphone' as PermissionName,
    });
    return status.state;
  } catch {
    return 'prompt'; // kn: Safari lacks the microphone permission query name; treat as unknown
  }
}

export class NotImplementedError extends Error {
  constructor() {
    super(
      'Audio capture is not wired to a real backend yet (see src/audio/capture.ts). ' +
        'No microphone data is sent anywhere by this build.',
    );
    this.name = 'NotImplementedError';
  }
}

/**
 * STUB. Matches the §7.2 signature exactly so callers (preflight, encounter) compile and run
 * against the real seam once WS4 ships a real AudioIO host to talk to. Deliberately throws
 * rather than returning a fake handle that looks like it works.
 */
export async function startCapture(_deviceId?: string): Promise<CaptureHandle> {
  throw new NotImplementedError();
}

/** A silent handle for UI development/tests that need a CaptureHandle shape without real audio. */
export function silentCaptureHandle(deviceId = 'stub'): CaptureHandle {
  const level = signal(0);
  const clipping = signal(false);
  return { deviceId, level, clipping, stop() {} };
}
