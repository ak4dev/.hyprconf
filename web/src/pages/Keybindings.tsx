import { useState, useMemo } from 'react';
import { SectionHeading, FilterBar, KeyboardKey } from '@/components/ui';
import { KEYBINDINGS } from '@/content';
import styles from './Keybindings.module.css';

export default function Keybindings() {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search) return KEYBINDINGS;
    const q = search.toLowerCase();
    return KEYBINDINGS.map((cat) => ({
      ...cat,
      bindings: cat.bindings.filter(
        (b) =>
          b.action.toLowerCase().includes(q) ||
          b.keys.some((k) => k.toLowerCase().includes(q))
      ),
    })).filter((cat) => cat.bindings.length > 0);
  }, [search]);

  return (
    <div className={styles.page}>
      <SectionHeading id="keybindings">Keybindings</SectionHeading>
      <p className={styles.intro}>
        All keybindings use <strong>Super</strong> (Windows key) as the main modifier.
        Fully customisable via <code>hyprconf keybinds</code>.
      </p>

      <FilterBar
        options={[]}
        activeValue=""
        onValueChange={() => {}}
        searchPlaceholder="Search keybindings…"
        searchValue={search}
        onSearchChange={setSearch}
      />

      {filtered.map((cat) => (
        <section key={cat.id}>
          <SectionHeading id={cat.id} level={2}>
            {cat.title}
          </SectionHeading>
          <div className={styles.table} role="table" aria-label={cat.title}>
            <div className={styles.thead} role="row">
              <span role="columnheader">Keys</span>
              <span role="columnheader">Action</span>
            </div>
            {cat.bindings.map((b, i) => (
              <div key={i} className={styles.row} role="row">
                <span role="cell">
                  <KeyboardKey keys={b.keys} />
                </span>
                <span role="cell" className={styles.action}>
                  {b.action}
                </span>
              </div>
            ))}
          </div>
        </section>
      ))}

      {filtered.length === 0 && (
        <p className={styles.empty}>No keybindings match your search.</p>
      )}
    </div>
  );
}
