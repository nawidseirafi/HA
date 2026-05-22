import type { MarketSignal } from '../../api/client';

export function MarketSignalBadge({ signal }: { signal: MarketSignal }) {
  return <span className={`market-signal ${signal}`}>{signalLabel(signal)}</span>;
}

export function signalLabel(signal: MarketSignal) {
  return {
    bullish: 'Bullish',
    neutral: 'Neutral',
    bearish: 'Bearish',
    watch: 'Watch',
  }[signal];
}
