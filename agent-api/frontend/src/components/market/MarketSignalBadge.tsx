import type { MarketSignal } from '../../api/client';

export function MarketSignalBadge({ signal }: { signal: MarketSignal }) {
  return <span className={`market-signal ${signal}`}>{signalLabel(signal)}</span>;
}

export function signalLabel(signal: MarketSignal) {
  return {
    buy: 'Buy',
    hold: 'Hold',
    sell: 'Sell',
    watch: 'Watch',
  }[signal];
}
