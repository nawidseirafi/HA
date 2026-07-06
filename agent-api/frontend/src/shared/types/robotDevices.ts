import type {WallEntity} from '@shared/api/client';

export type RobotDeviceEntity = WallEntity & {
  supported_features?: number | null;
  battery_level?: number | null;
  last_updated?: string | null;
  available?: boolean;
};

export type LawnMowerEntity = RobotDeviceEntity & {
  raw_status?: string | null;
  state:
    | 'docked'
    | 'mowing'
    | 'paused'
    | 'returning'
    | 'charging'
    | 'idle'
    | 'unavailable'
    | 'error'
    | string;
};
