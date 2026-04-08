type JsonValue = Record<string, unknown>;

export type ControlApiConfig = {
  baseUrl: string;
  token: string;
};

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export class ControlApiClient {
  private readonly baseUrl: string;
  private readonly token: string;

  constructor(config: ControlApiConfig) {
    this.baseUrl = trimTrailingSlash(config.baseUrl);
    this.token = config.token;
  }

  async get(path: string): Promise<JsonValue> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${this.token}`,
      },
    });
    return this.parseResponse(response);
  }

  async post(path: string, body: JsonValue): Promise<JsonValue> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    return this.parseResponse(response);
  }

  async patch(path: string, body: JsonValue): Promise<JsonValue> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    return this.parseResponse(response);
  }

  private async parseResponse(response: Response): Promise<JsonValue> {
    const text = await response.text();
    const payload = text ? (JSON.parse(text) as JsonValue) : {};
    if (!response.ok) {
      throw new Error(`Control API error ${response.status}: ${JSON.stringify(payload)}`);
    }
    return payload;
  }
}

export function createControlApiClient(pluginConfig: Record<string, unknown> | undefined): ControlApiClient {
  const baseUrl = String(pluginConfig?.controlApiBaseUrl ?? "");
  const token = String(pluginConfig?.controlApiToken ?? "");

  if (!baseUrl || !token) {
    throw new Error("studio-control plugin requires controlApiBaseUrl and controlApiToken");
  }

  return new ControlApiClient({ baseUrl, token });
}
