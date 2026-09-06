# Security

The backend validates JWT signatures and looks up the current role in the database. Viewers cannot approve or execute actions. Unknown actions, unknown targets, and arbitrary execution endpoints are rejected. Docker failures are reported as failures. External documents and LLM output are data only; only registry actions can mutate services.
