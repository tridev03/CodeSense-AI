"use client";

import { useState, useEffect, useCallback } from "react";
import { statusApi, SystemStatusResponse } from "@/lib/api";

export type ConnectionHealth = "connected" | "degraded" | "offline";

export function useBackendStatus(pollIntervalMs = 30000) {
  const [services, setServices] = useState<SystemStatusResponse | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkStatus = useCallback(async () => {
    setIsChecking(true);
    try {
      const data = await statusApi.get();
      setServices(data);
      setError(null);
    } catch (err) {
      setServices(null);
      setError(err instanceof Error ? err.message : "Backend unreachable");
    } finally {
      setIsChecking(false);
    }
  }, []);

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, pollIntervalMs);
    return () => clearInterval(interval);
  }, [checkStatus, pollIntervalMs]);

  const isOnline = !!services && services.backend === "ok";

  const health: ConnectionHealth = !isOnline
    ? "offline"
    : services.database === "ok" && services.qdrant === "ok"
    ? "connected"
    : "degraded";

  return {
    isOnline,
    health,
    services,
    isChecking,
    error,
    refresh: checkStatus,
  };
}

