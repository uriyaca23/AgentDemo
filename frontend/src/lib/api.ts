/**
 * Shared API configuration.
 * In Docker, set NEXT_PUBLIC_API_URL to point at the backend container.
 * Locally, defaults to http://localhost:8001.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
