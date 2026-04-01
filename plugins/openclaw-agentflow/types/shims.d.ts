declare module "openclaw/plugin-sdk/core" {
  export function definePluginEntry(entry: any): any;
}

declare module "node:child_process" {
  export function execFile(...args: any[]): any;
}

declare module "node:fs" {
  export function existsSync(path: string): boolean;
}

declare module "node:path" {
  export function dirname(path: string): string;
  export function join(...segments: string[]): string;
  export function resolve(...segments: string[]): string;
}

declare module "node:fs/promises" {
  export function writeFile(path: string, data: string, encoding?: string): Promise<void>;
  export function rm(path: string, options?: { force?: boolean }): Promise<void>;
}

declare module "node:os" {
  export function tmpdir(): string;
}

declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}

declare module "node:util" {
  export function promisify(fn: any): any;
}

declare var process: any;
