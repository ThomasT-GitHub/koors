/**
 * Backend Configuration
 *
 * To change the backend server address, edit the values below.
 * This makes it easy to switch between different network environments
 * without editing application code.
 */

export const BACKEND_CONFIG = {
  /**
   * Backend server IP address or hostname
   * Default: 172.20.10.7 (current setup)
   *
   * Common scenarios:
   * - Local hotspot: 172.20.10.x
   * - Local WiFi: 192.168.x.x
   * - Localhost (simulator only): localhost
   */
  HOST: "172.20.10.14",

  /**
   * Backend server port
   * Default: 8080
   */
  PORT: 8080,

  /**
   * Full base URL (auto-constructed)
   */
  get BASE_URL() {
    return `http://${this.HOST}:${this.PORT}`;
  }
} as const;
