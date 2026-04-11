import { Link } from 'react-router-dom';
import styles from './NotFound.module.css';

export default function NotFound() {
  return (
    <div className={styles.page}>
      <span className={styles.code}>404</span>
      <p className={styles.message}>Page not found</p>
      <Link to="/" className={styles.link}>
        ← Back to home
      </Link>
    </div>
  );
}
