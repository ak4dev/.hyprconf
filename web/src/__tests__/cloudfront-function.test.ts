import { describe, it, expect } from 'vitest';

/**
 * Unit tests for the CloudFront Function logic.
 * We extract the handler function as a plain JS function and test it directly.
 */
function handler(event: { request: { uri: string; headers: Record<string, { value: string }> } }) {
  const request = event.request;
  const ua = (request.headers['user-agent'] || { value: '' }).value;

  if (/curl|wget/i.test(ua)) {
    request.uri = '/install.sh';
    return request;
  }

  if (request.uri === '/' || !/\.\w+$/.test(request.uri)) {
    request.uri = '/index.html';
  }
  return request;
}

function makeEvent(uri: string, userAgent: string) {
  return {
    request: {
      uri,
      headers: { 'user-agent': { value: userAgent } },
    },
  };
}

describe('CloudFront Function (hyprconf-ua-router)', () => {
  it('curl UA → /install.sh', () => {
    const result = handler(makeEvent('/', 'curl/7.88.1'));
    expect(result.uri).toBe('/install.sh');
  });

  it('wget UA → /install.sh', () => {
    const result = handler(makeEvent('/', 'Wget/1.21'));
    expect(result.uri).toBe('/install.sh');
  });

  it('curl UA on any path → /install.sh', () => {
    const result = handler(makeEvent('/themes', 'curl/7.88.1'));
    expect(result.uri).toBe('/install.sh');
  });

  it('browser UA on / → /index.html', () => {
    const result = handler(makeEvent('/', 'Mozilla/5.0'));
    expect(result.uri).toBe('/index.html');
  });

  it('browser UA on /themes → /index.html (SPA route)', () => {
    const result = handler(makeEvent('/themes', 'Mozilla/5.0'));
    expect(result.uri).toBe('/index.html');
  });

  it('browser UA on /cli → /index.html (SPA route)', () => {
    const result = handler(makeEvent('/cli', 'Mozilla/5.0'));
    expect(result.uri).toBe('/index.html');
  });

  it('browser UA on /assets/style.css → passes through (static asset)', () => {
    const result = handler(makeEvent('/assets/style.css', 'Mozilla/5.0'));
    expect(result.uri).toBe('/assets/style.css');
  });

  it('browser UA on /assets/index-abc.js → passes through', () => {
    const result = handler(makeEvent('/assets/index-abc.js', 'Mozilla/5.0'));
    expect(result.uri).toBe('/assets/index-abc.js');
  });

  it('empty UA → /index.html', () => {
    const result = handler(makeEvent('/', ''));
    expect(result.uri).toBe('/index.html');
  });

  it('missing user-agent header → /index.html', () => {
    const result = handler({
      request: { uri: '/', headers: {} as Record<string, { value: string }> },
    });
    expect(result.uri).toBe('/index.html');
  });

  it('browser UA on /install.sh → passes through (static file)', () => {
    const result = handler(makeEvent('/install.sh', 'Mozilla/5.0'));
    expect(result.uri).toBe('/install.sh');
  });

  it('browser UA on /favicon.ico → passes through', () => {
    const result = handler(makeEvent('/favicon.ico', 'Mozilla/5.0'));
    expect(result.uri).toBe('/favicon.ico');
  });

  it('browser UA on deeply nested SPA route → /index.html', () => {
    const result = handler(makeEvent('/keybindings/movement', 'Mozilla/5.0'));
    expect(result.uri).toBe('/index.html');
  });

  it('curl with custom UA string → /install.sh', () => {
    const result = handler(makeEvent('/', 'curl/8.0.0 (custom build)'));
    expect(result.uri).toBe('/install.sh');
  });
});
