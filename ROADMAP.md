# Roadmap

DataContext is early and intentionally small. This roadmap focuses on making the current attribution model useful before expanding the integration surface.

## Near Term

- Improve examples for common application and worker patterns.
- Add focused integration guidance for popular database wrappers and ORMs, starting with SQLAlchemy.
- Explore Snowflake support and other notable data libraries based on community demand.
- Tighten event schema documentation as real usage patterns emerge.
- Keep the core event shape small and stable.

## Later

- Explore first-party integrations for common Python database clients.
- Add more sink examples for observability and data platforms.
- Improve callsite attribution controls for larger applications.
- Evaluate lightweight configuration from environment variables.

## Prioritization

Integration priorities should be driven by real usage. Open a GitHub Discussion or feature request with the library, current data-access pattern, and the event fields needed.

## Non-Goals For Now

- Replacing existing tracing or logging pipelines.
- Capturing raw query text by default.
- Automatically instrumenting every database driver.
- Adding a hosted service or control plane.
