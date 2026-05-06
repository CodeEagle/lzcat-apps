import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { SupportedLanguage } from '../i18n'

interface UserInfo {
  name: string
  role: string
}

interface AppState {
  siderCollapsed: boolean
  user: UserInfo
  language: SupportedLanguage
  setUser: (user: Partial<UserInfo>) => void
  setLanguage: (lang: SupportedLanguage) => void
  toggleSider: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      siderCollapsed: false,
      user: {
        name: 'Admin',
        role: '系统管理员',
      },
      language: 'zh-CN',
      setUser: (user) =>
        set((state) => ({
          user: {
            ...state.user,
            ...user,
          },
        })),
      setLanguage: (lang) => set(() => ({ language: lang })),
      toggleSider: () =>
        set((state) => ({
          siderCollapsed: !state.siderCollapsed,
        })),
    }),
    {
      name: 'jellyfish-app-store',
      partialize: (state) => ({
        siderCollapsed: state.siderCollapsed,
        user: state.user,
        language: state.language,
      }),
    },
  ),
)
