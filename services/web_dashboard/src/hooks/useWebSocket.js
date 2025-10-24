import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import defaultClient, { getWebSocketClient } from "../lib/websocket.js";

function resolveClient(options = {}) {
  if (!options || Object.keys(options).length === 0) {
    return defaultClient;
  }
  return getWebSocketClient(options);
}

export default function useWebSocket(options = {}) {
  const {
    url,
    autoConnect = true,
    disconnectOnUnmount = false,
    reconnectDelay,
    maxReconnectDelay,
    autoReconnect,
  } = options;

  const clientOptions = useMemo(() => {
    const next = {};
    if (url) {
      next.url = url;
    }
    if (reconnectDelay !== undefined) {
      next.reconnectDelay = reconnectDelay;
    }
    if (maxReconnectDelay !== undefined) {
      next.maxReconnectDelay = maxReconnectDelay;
    }
    if (autoReconnect !== undefined) {
      next.autoReconnect = autoReconnect;
    }
    return next;
  }, [url, reconnectDelay, maxReconnectDelay, autoReconnect]);

  const clientRef = useRef(null);
  const [connection, setConnection] = useState({ status: "idle", error: null, attempt: 0 });

  useEffect(() => {
    const client = resolveClient(clientOptions);
    clientRef.current = client;
    const unsubscribeStatus = client.onStatusChange((details) => {
      setConnection(details);
    });

    if (autoConnect !== false) {
      client.connect();
    }

    return () => {
      unsubscribeStatus();
      if (disconnectOnUnmount) {
        client.disconnect({ preventReconnect: true });
      }
    };
  }, [clientOptions, autoConnect, disconnectOnUnmount]);

  const subscribe = useCallback((types, handler) => {
    const client = clientRef.current;
    if (!client) {
      return () => {};
    }
    return client.subscribe(types, handler);
  }, []);

  const publish = useCallback((type, payload, raw) => {
    const client = clientRef.current;
    if (!client) {
      return;
    }
    client.publish(type, payload, raw);
  }, []);

  const reconnect = useCallback(() => {
    const client = clientRef.current;
    if (!client) {
      return;
    }
    client.reconnect();
  }, []);

  const disconnect = useCallback(
    (optionsArg = { preventReconnect: true }) => {
      const client = clientRef.current;
      if (!client) {
        return;
      }
      client.disconnect(optionsArg);
    },
    []
  );

  return useMemo(
    () => ({
      status: connection.status,
      error: connection.error,
      attempt: connection.attempt,
      isConnected: connection.status === "open",
      subscribe,
      publish,
      reconnect,
      disconnect,
      client: clientRef.current,
    }),
    [connection, subscribe, publish, reconnect, disconnect]
  );
}
