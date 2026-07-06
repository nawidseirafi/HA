import {useMemo, useState} from 'react';
import {api} from '@shared/api/client';
import type {LawnMowerEntity} from '@shared/types/robotDevices';

const LAWN_MOWER_FEATURE_START_MOWING = 1;
const LAWN_MOWER_FEATURE_PAUSE = 2;
const LAWN_MOWER_FEATURE_DOCK = 4;

export type LawnMowerAction = 'start_mowing' | 'pause' | 'dock';

export function useLawnMower(mower: LawnMowerEntity, onUpdated?: () => void) {
  const [busyAction, setBusyAction] = useState<LawnMowerAction | ''>('');
  const offline = isMowerOffline(mower);

  const actions = useMemo(() => ({
    start: {
      service: 'start_mowing' as const,
      supported: mowerSupports(mower, LAWN_MOWER_FEATURE_START_MOWING),
      disabled: offline || busyAction !== '' || !mowerSupports(mower, LAWN_MOWER_FEATURE_START_MOWING),
    },
    pause: {
      service: 'pause' as const,
      supported: mowerSupports(mower, LAWN_MOWER_FEATURE_PAUSE),
      disabled: offline || busyAction !== '' || !mowerSupports(mower, LAWN_MOWER_FEATURE_PAUSE),
    },
    dock: {
      service: 'dock' as const,
      supported: mowerSupports(mower, LAWN_MOWER_FEATURE_DOCK),
      disabled: offline || busyAction !== '' || !mowerSupports(mower, LAWN_MOWER_FEATURE_DOCK),
    },
  }), [busyAction, mower, offline]);

  const call = async (service: LawnMowerAction) => {
    setBusyAction(service);
    try {
      await api.callHomeAssistantService({
        domain: 'lawn_mower',
        service,
        entity_id: mower.entity_id,
      });
      onUpdated?.();
    } finally {
      setBusyAction('');
    }
  };

  return {
    actions,
    busyAction,
    offline,
    call,
  };
}

export function mowerSupports(mower: LawnMowerEntity, feature: number) {
  return typeof mower.supported_features === 'number' && (mower.supported_features & feature) === feature;
}

export function isMowerOffline(mower: LawnMowerEntity) {
  const state = String(mower.state || '').toLowerCase();
  return mower.available === false || state === 'unavailable' || state === 'unknown';
}
