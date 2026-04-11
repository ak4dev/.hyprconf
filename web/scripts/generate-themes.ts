/**
 * Build-time script: reads all theme JSON files from the hyprconf dotfiles
 * and generates a TypeScript module at src/generated/themes.ts.
 *
 * Run: npm run generate-themes
 * Auto-runs as prebuild/predev via package.json scripts.
 */

import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const THEMES_DIR = path.resolve(
  __dirname,
  '../../stow/hypr/.config/hypr/scripts/theme-switcher/themes'
);
const OUTPUT_FILE = path.resolve(__dirname, '../src/generated/themes.ts');

const REQUIRED_KEYS = ['background', 'foreground', 'accent', 'comment', 'appearance'] as const;
const OPTIONAL_COLOUR_KEYS = ['cyan', 'green', 'orange', 'pink', 'purple', 'red', 'yellow'] as const;

interface RawTheme {
  background: string;
  foreground: string;
  accent: string;
  comment: string;
  appearance: 'dark' | 'light';
  cyan?: string;
  green?: string;
  orange?: string;
  pink?: string;
  purple?: string;
  red?: string;
  yellow?: string;
  kitty?: string;
  vscode?: { theme: string; extension: string; font?: string };
  firefox?: { theme_name: string; theme_id: string };
  wallpaper?: string;
  btop?: string;
}

function main(): void {
  const files = fs.readdirSync(THEMES_DIR).filter((f) => f.endsWith('.json')).sort();

  if (files.length === 0) {
    console.error(`No theme JSON files found in ${THEMES_DIR}`);
    process.exit(1);
  }

  const themes: Record<string, RawTheme> = {};
  const errors: string[] = [];

  for (const file of files) {
    const name = file.replace(/\.json$/, '');
    const filePath = path.join(THEMES_DIR, file);
    const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as Record<string, unknown>;

    for (const key of REQUIRED_KEYS) {
      if (!raw[key]) {
        errors.push(`${file}: missing required key "${key}"`);
      }
    }

    themes[name] = {
      background: String(raw['background'] ?? '#000000'),
      foreground: String(raw['foreground'] ?? '#ffffff'),
      accent: String(raw['accent'] ?? '#0088ff'),
      comment: String(raw['comment'] ?? '#666666'),
      appearance: raw['appearance'] === 'light' ? 'light' : 'dark',
      ...(raw['cyan'] ? { cyan: String(raw['cyan']) } : {}),
      ...(raw['green'] ? { green: String(raw['green']) } : {}),
      ...(raw['orange'] ? { orange: String(raw['orange']) } : {}),
      ...(raw['pink'] ? { pink: String(raw['pink']) } : {}),
      ...(raw['purple'] ? { purple: String(raw['purple']) } : {}),
      ...(raw['red'] ? { red: String(raw['red']) } : {}),
      ...(raw['yellow'] ? { yellow: String(raw['yellow']) } : {}),
    };
  }

  if (errors.length > 0) {
    console.error('Theme validation errors:');
    errors.forEach((e) => console.error(`  - ${e}`));
    process.exit(1);
  }

  const communityThemes = Object.keys(themes)
    .filter((n) => !n.startsWith('ai:'))
    .sort();
  const aiThemes = Object.keys(themes)
    .filter((n) => n.startsWith('ai:'))
    .sort();
  const allNames = [...communityThemes, ...aiThemes];

  const output = `// AUTO-GENERATED — DO NOT EDIT
// Generated from theme JSON files in stow/hypr/.config/hypr/scripts/theme-switcher/themes/
// Run: npm run generate-themes

export interface Theme {
  background: string;
  foreground: string;
  accent: string;
  comment: string;
  appearance: 'dark' | 'light';
  cyan?: string;
  green?: string;
  orange?: string;
  pink?: string;
  purple?: string;
  red?: string;
  yellow?: string;
}

export const themes: Record<string, Theme> = ${JSON.stringify(themes, null, 2)} as const;

export const themeNames: string[] = ${JSON.stringify(allNames, null, 2)};

export const communityThemeNames: string[] = ${JSON.stringify(communityThemes, null, 2)};

export const aiThemeNames: string[] = ${JSON.stringify(aiThemes, null, 2)};

export const defaultThemeName = 'ai:circuit';

export const themeCount = ${allNames.length};
`;

  fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
  fs.writeFileSync(OUTPUT_FILE, output, 'utf-8');
  console.log(`Generated ${OUTPUT_FILE} with ${allNames.length} themes (${communityThemes.length} community, ${aiThemes.length} AI-original)`);
}

main();
