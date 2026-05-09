import { useEffect, useEffectEvent } from 'react';

type UsePollingOptions = {
  enabled?: boolean;
  runImmediately?: boolean;
  refreshOnFocus?: boolean;
  onlyWhenVisible?: boolean;
};

export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  {
    enabled = true,
    runImmediately = true,
    refreshOnFocus = true,
    onlyWhenVisible = true,
  }: UsePollingOptions = {},
): void {
  const onTick = useEffectEvent(() => {
    if (onlyWhenVisible && document.visibilityState !== 'visible') {
      return;
    }
    void callback();
  });

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    if (runImmediately) {
      void onTick();
    }

    const intervalId = window.setInterval(() => {
      void onTick();
    }, intervalMs);

    const handleFocus = () => {
      void onTick();
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void onTick();
      }
    };

    if (refreshOnFocus) {
      window.addEventListener('focus', handleFocus);
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    return () => {
      window.clearInterval(intervalId);
      if (refreshOnFocus) {
        window.removeEventListener('focus', handleFocus);
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
    };
  }, [enabled, intervalMs, onTick, onlyWhenVisible, refreshOnFocus, runImmediately]);
}
