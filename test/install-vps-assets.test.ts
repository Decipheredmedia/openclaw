import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import JSON5 from "json5";
import { describe, expect, it } from "vitest";
import { validateConfigObjectWithPlugins } from "../src/config/validation.js";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

type TemplateConfig = {
  gateway: {
    bind: string;
    port: number;
  };
  channels: {
    telegram: {
      enabled: boolean;
    };
  };
  models: {
    providers: Record<
      string,
      {
        baseUrl?: string;
      }
    >;
  };
  skills: {
    load: {
      extraDirs: string[];
    };
    entries: Record<
      string,
      {
        enabled?: boolean;
      }
    >;
  };
};

function readRepoFile(relativePath: string): string {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

describe("VPS install assets", () => {
  it("ships shell installers with valid bash syntax", () => {
    execFileSync("bash", ["-n", path.join(repoRoot, "install-vps.sh")], { stdio: "pipe" });
    execFileSync("bash", ["-n", path.join(repoRoot, "install", "install-skills.sh")], {
      stdio: "pipe",
    });
  });

  it("provides a valid OpenClaw config template for the Venice VPS flow", () => {
    const raw = readRepoFile("install/openclaw.json.template");
    const parsed = JSON5.parse(raw) as TemplateConfig;
    const result = validateConfigObjectWithPlugins(parsed, {
      env: {
        OPENAI_API_KEY: "venice-test-key",
        OPENCLAW_GATEWAY_TOKEN: "gateway-test-token",
        TELEGRAM_BOT_TOKEN: "123456:ABCDEF",
      },
    });

    if (!result.ok) {
      throw new Error(JSON.stringify(result.issues, null, 2));
    }

    expect(parsed.gateway.bind).toBe("lan");
    expect(parsed.gateway.port).toBe(18789);
    expect(parsed.channels.telegram.enabled).toBe(true);
    expect(parsed.models.providers["venice-openai"].baseUrl).toBe("https://api.venice.ai/v1");
    expect(parsed.skills.load.extraDirs).toEqual(["/root/.openclaw/skills"]);
    expect(parsed.skills.entries["ai-and-llms"].enabled).toBe(true);
    expect(parsed.skills.entries["web-and-frontend-development"].enabled).toBe(true);
  });

  it("includes the required Venice deployment placeholders and service assets", () => {
    const envTemplate = readRepoFile("install/.env.template");
    const installer = readRepoFile("install-vps.sh");
    const skillInstaller = readRepoFile("install/install-skills.sh");
    const serviceUnit = readRepoFile("install/openclaw-gateway.service");
    const composeFile = readRepoFile("install/docker-compose.venice.yml");
    const readme = readRepoFile("install/README-VPS.md");

    expect(envTemplate).toContain("OPENAI_API_KEY=__VENICE_API_KEY__");
    expect(envTemplate).toContain("OPENCLAW_GATEWAY_TOKEN=__GATEWAY_TOKEN__");
    expect(envTemplate).toContain("TELEGRAM_BOT_TOKEN=__TELEGRAM_BOT_TOKEN__");

    expect(installer).toContain("curl -fsSL https://deb.nodesource.com/setup_22.x | bash -");
    expect(installer).toContain("pnpm build:docker");
    expect(installer).toContain("pnpm ui:build");
    expect(installer).toContain('bash "$OPENCLAW_DIR/install/install-skills.sh"');

    expect(skillInstaller).toContain("REFERENCE.md");
    expect(skillInstaller).toContain("SKILL.md");
    expect(skillInstaller).toContain('"type": "category-catalog"');

    expect(serviceUnit).toContain("EnvironmentFile=/root/.openclaw/.env");
    expect(serviceUnit).toContain(
      "ExecStart=/usr/bin/node /opt/openclaw/openclaw.mjs gateway --bind lan --port 18789",
    );

    expect(composeFile).toContain("ghcr.io/openclaw/openclaw:latest");
    expect(composeFile).toContain('"18789:18789"');
    expect(composeFile).toContain('"18790:18790"');

    expect(readme).toContain(
      "curl -fsSL https://raw.githubusercontent.com/Decipheredmedia/openclaw/main/install-vps.sh | bash",
    );
    expect(readme).toContain("journalctl -u openclaw-gateway -f");
    expect(readme).toContain("https://venice.ai/settings");
  });
});
