import { lazy, type ComponentType } from 'react';
import { Palette, Keyboard, Terminal, Download } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface RouteConfig {
  path: string;
  title: string;
  component: React.LazyExoticComponent<ComponentType>;
  icon: LucideIcon;
  showInNav: boolean;
}

export const routes: RouteConfig[] = [
  {
    path: '/themes',
    title: 'Themes',
    component: lazy(() => import('@/pages/Themes')),
    icon: Palette,
    showInNav: true,
  },
  {
    path: '/keybindings',
    title: 'Keybindings',
    component: lazy(() => import('@/pages/Keybindings')),
    icon: Keyboard,
    showInNav: true,
  },
  {
    path: '/cli',
    title: 'CLI',
    component: lazy(() => import('@/pages/CLI')),
    icon: Terminal,
    showInNav: true,
  },
  {
    path: '/install',
    title: 'Install',
    component: lazy(() => import('@/pages/Install')),
    icon: Download,
    showInNav: true,
  },
];
