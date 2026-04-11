import { describe, it, expect } from 'vitest';
import {
  FEATURES,
  CLI_GROUPS,
  KEYBINDINGS,
  INSTALL_MODES,
} from '@/content';

describe('content.ts data integrity', () => {
  describe('FEATURES', () => {
    it('is a non-empty array', () => {
      expect(FEATURES.length).toBeGreaterThan(0);
    });

    it('every feature has title and description', () => {
      for (const f of FEATURES) {
        expect(f.title).toBeTruthy();
        expect(f.description).toBeTruthy();
      }
    });
  });

  describe('CLI_GROUPS', () => {
    it('is a non-empty array', () => {
      expect(CLI_GROUPS.length).toBeGreaterThan(0);
    });

    it('every group has title and non-empty commands', () => {
      for (const g of CLI_GROUPS) {
        expect(g.title).toBeTruthy();
        expect(g.commands.length).toBeGreaterThan(0);
      }
    });

    it('every command has name, usage, and description', () => {
      for (const g of CLI_GROUPS) {
        for (const cmd of g.commands) {
          expect(cmd.name).toBeTruthy();
          expect(cmd.usage).toBeTruthy();
          expect(cmd.description).toBeTruthy();
        }
      }
    });

    it('uses singular "show keybind" not plural', () => {
      const allNames = CLI_GROUPS.flatMap((g) => g.commands.map((c) => c.name));
      const showKeybind = allNames.filter((n) => n.includes('show keybind'));
      expect(showKeybind.length).toBe(1);
      expect(showKeybind[0]).toBe('hyprconf show keybind');
    });

    it('includes workspace update command', () => {
      const allNames = CLI_GROUPS.flatMap((g) => g.commands.map((c) => c.name));
      expect(allNames).toContain('hyprconf rule workspace update');
    });
  });

  describe('KEYBINDINGS', () => {
    it('is a non-empty array', () => {
      expect(KEYBINDINGS.length).toBeGreaterThan(0);
    });

    it('every category has title, id, and bindings', () => {
      for (const cat of KEYBINDINGS) {
        expect(cat.title).toBeTruthy();
        expect(cat.id).toBeTruthy();
        expect(cat.bindings.length).toBeGreaterThan(0);
      }
    });

    it('every binding has keys array and action', () => {
      for (const cat of KEYBINDINGS) {
        for (const b of cat.bindings) {
          expect(b.keys.length).toBeGreaterThan(0);
          expect(b.action).toBeTruthy();
        }
      }
    });

    it('includes Super+Shift+Q exit keybind', () => {
      const allBindings = KEYBINDINGS.flatMap((c) => c.bindings);
      const exitBind = allBindings.find(
        (b) => b.keys.includes('Super') && b.keys.includes('Shift') && b.keys.includes('Q')
      );
      expect(exitBind).toBeDefined();
      expect(exitBind!.action).toMatch(/exit/i);
    });

    it('has unique category IDs', () => {
      const ids = KEYBINDINGS.map((c) => c.id);
      expect(new Set(ids).size).toBe(ids.length);
    });
  });

  describe('INSTALL_MODES', () => {
    it('is a non-empty array', () => {
      expect(INSTALL_MODES.length).toBeGreaterThan(0);
    });

    it('every mode has title and description', () => {
      for (const m of INSTALL_MODES) {
        expect(m.title).toBeTruthy();
        expect(m.description).toBeTruthy();
      }
    });
  });
});
