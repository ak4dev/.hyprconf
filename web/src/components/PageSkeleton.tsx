import styles from './PageSkeleton.module.css';

export function PageSkeleton() {
  return (
    <div className={styles.skeleton} aria-label="Loading page…" role="status">
      <div className={styles.bar} style={{ width: '40%', height: '2rem' }} />
      <div className={styles.bar} style={{ width: '80%' }} />
      <div className={styles.bar} style={{ width: '65%' }} />
      <div className={styles.bar} style={{ width: '75%' }} />
      <div className={styles.grid}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className={styles.cardPlaceholder} />
        ))}
      </div>
    </div>
  );
}
