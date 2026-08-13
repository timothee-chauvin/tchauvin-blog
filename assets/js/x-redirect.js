// The /x/ landing page redirects to the curated tree. The meta-refresh fallback
// drops the URL hash, which the owner tooling relies on (#curate / #curate-off);
// replace() preserves it and leaves no history entry.
location.replace('/x/curated/' + location.hash);
