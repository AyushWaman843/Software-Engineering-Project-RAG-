/** Fired before programmatic client navigations to show the route progress bar. */
export function signalRouteStart() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("route-start"));
  }
}
