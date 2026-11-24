// The Kiro Crew host provides these modules at run time. They are not on npm,
// so the page declares the few names it uses.

declare module '@kirocrew/app-sdk' {
  export interface AppApi {
    get<T = unknown>(path: string): Promise<T>
    post<T = unknown>(path: string, body?: unknown): Promise<T>
    put<T = unknown>(path: string, body?: unknown): Promise<T>
    patch<T = unknown>(path: string, body?: unknown): Promise<T>
  }
  export function useAppApi(): AppApi
  export function useNotify(): (message: string, opts?: { type?: 'info' | 'success' | 'error' }) => void
  export function useTheme(): { mode: 'dark' | 'light'; accent: string; colorTheme: string }
  export function useNavBadge(): (count: number) => void
}

declare module '@kirocrew/app-sdk/ui' {
  import type { ButtonHTMLAttributes, FC, HTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
  export const PageHeader: FC<{ title: ReactNode; subtitle?: string; actions?: ReactNode }>
  export const Card: FC<HTMLAttributes<HTMLDivElement>>
  export const CardTitle: FC<{ children?: ReactNode }>
  export const Btn: FC<ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean; primary?: boolean; busy?: boolean }>
  export const Input: FC<InputHTMLAttributes<HTMLInputElement>>
  export const Badge: FC<{ variant: 'ok' | 'err' | 'warn' | 'aim' | 'muted'; children: ReactNode; title?: string }>
  export const StatCard: FC<{ label: string; value?: string | number | null; accent?: boolean; title?: string }>
  export const SegmentedControl: FC<{
    segments: { key: string; label: string; count?: number }[]
    value: string
    onChange: (key: string) => void
    ariaLabel?: string
    layoutId?: string
  }>
}
