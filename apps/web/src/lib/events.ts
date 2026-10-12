import type { Event } from "./api";
export function eventSocket(cursor: number, onEvent: (event: Event) => void, onClose: () => void) {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/ws/events`);
  socket.onopen = () => socket.send(JSON.stringify({ cursor }));
  socket.onmessage = (message) => onEvent(JSON.parse(message.data) as Event);
  socket.onclose = onClose;
  return socket;
}
