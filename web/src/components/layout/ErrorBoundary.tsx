import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div
          style={{
            padding: 'var(--hc-space-8)',
            maxWidth: 'var(--hc-content-max)',
            margin: '0 auto',
          }}
        >
          <div
            style={{
              padding: 'var(--hc-space-6)',
              background: 'var(--hc-bg-elevated)',
              border: '1px solid var(--hc-border-color)',
              borderRadius: 'var(--hc-radius-md)',
              fontFamily: 'var(--hc-font-mono)',
            }}
          >
            <h2 style={{ color: 'var(--hc-red, var(--hc-accent))', margin: '0 0 var(--hc-space-4)' }}>
              Something went wrong
            </h2>
            <p style={{ color: 'var(--hc-fg-muted)', fontSize: 'var(--hc-font-size-sm)' }}>
              {this.state.error.message}
            </p>
            <button
              onClick={() => this.setState({ error: null })}
              style={{
                marginTop: 'var(--hc-space-4)',
                padding: 'var(--hc-space-2) var(--hc-space-4)',
                background: 'var(--hc-accent-muted)',
                border: '1px solid var(--hc-accent)',
                borderRadius: 'var(--hc-radius-sm)',
                color: 'var(--hc-accent)',
                fontFamily: 'var(--hc-font-mono)',
                fontSize: 'var(--hc-font-size-sm)',
                cursor: 'pointer',
              }}
            >
              Retry
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
