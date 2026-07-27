import { useCallback, useState } from 'react';

export type PodcastScreen = 'create' | 'player' | 'history';

export interface UsePodcastNavigationResult {
  currentScreen: PodcastScreen;
  setCurrentScreen: (screen: PodcastScreen) => void;
  goToPlayer: () => void;
  goToCreate: () => void;
  goToHistory: () => void;
}

export const usePodcastNavigation = (): UsePodcastNavigationResult => {
  const [currentScreen, setCurrentScreen] = useState<PodcastScreen>('create');

  const goToPlayer = useCallback(() => {
    setCurrentScreen('player');
  }, []);

  const goToCreate = useCallback(() => {
    setCurrentScreen('create');
  }, []);

  const goToHistory = useCallback(() => {
    setCurrentScreen('history');
  }, []);

  return {
    currentScreen,
    setCurrentScreen,
    goToPlayer,
    goToCreate,
    goToHistory,
  };
};
