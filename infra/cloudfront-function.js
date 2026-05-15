// CloudFront Function: hyprconf-ua-router
// Stage: viewer-request | Runtime: cloudfront-js-2.0
//
// Routing logic:
//   curl/wget  → /install.sh   (preserves: curl -fsSL hyprconf.sh | bash)
//   browser /  → /index.html   (React SPA entry)
//   browser /themes → /index.html (SPA client-side routing)
//   browser /foo.js → /foo.js  (static asset passthrough)

function handler(event) {
  var request = event.request;
  var ua = (request.headers['user-agent'] || { value: '' }).value;

  // CLI tools (curl/wget) get the install script. Match leading product token
  // to avoid false positives like "Curlybot" appearing inside browser UAs.
  if (/^(curl|wget)\//i.test(ua)) {
    request.uri = '/install.sh';
    return request;
  }

  // SPA routing: non-file URIs → index.html
  if (request.uri === '/' || !/\.\w+$/.test(request.uri)) {
    request.uri = '/index.html';
  }

  return request;
}
