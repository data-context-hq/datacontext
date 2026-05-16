# Roadmap

DataContext is early and intentionally small. This roadmap focuses on making the current attribution model useful before expanding the integration surface.

## Near Term

- Add SQLAlchemy integration guidance for common engine/session patterns.
- Explore Snowflake support for teams using Python services and data-platform workloads.
- Improve examples for production application and worker patterns.
- Tighten event schema documentation as real usage patterns emerge.
- Keep the core event shape small and stable.

## Later

- Explore first-party integrations for common Python database clients.
- Add more sink examples for observability and data platforms.
- Improve callsite attribution controls for larger applications.
- Evaluate lightweight configuration from environment variables.

## Prioritization

Integration priorities should be driven by real usage. Open a GitHub Discussion or feature request with:

- the library or data platform,
- the current data-access pattern,
- sync or async usage,
- the event fields needed for production debugging or attribution.

## Non-Goals For Now

- Replacing existing tracing or logging pipelines.
- Capturing raw query text by default.
- Automatically instrumenting every database driver.
- Adding a hosted service or control plane.
