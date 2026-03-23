from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old in text:
        path.write_text(text.replace(old, new, 1))
        return
    if new in text:
        return
    raise RuntimeError(f"Expected snippet not found in {path}")


def patch_token_healthcheck(source_root: Path) -> None:
    path = source_root / "src" / "lib" / "tokenHealthCheck.ts"
    old = (
        "function isHealthCheckDisabled(): boolean {\n"
        '  return isEnvFlagEnabled("OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK") || process.env.NODE_ENV === "test";\n'
        "}\n"
    )
    new = (
        "function isHealthCheckDisabled(): boolean {\n"
        "  return (\n"
        '    isEnvFlagEnabled("OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK") ||\n'
        '    process.env.NODE_ENV === "test" ||\n'
        '    process.env.NEXT_PHASE === "phase-production-build"\n'
        "  );\n"
        "}\n"
    )
    replace_once(path, old, new)


def patch_cloud_sync_init(source_root: Path) -> None:
    path = source_root / "src" / "lib" / "initCloudSync.ts"
    old = (
        'import initializeCloudSync from "@/shared/services/initializeCloudSync";\n'
        'import "@/lib/tokenHealthCheck"; // Proactive token health-check scheduler\n'
        "\n"
        "// Initialize cloud sync when this module is imported\n"
        "let initialized = false;\n"
    )
    new = (
        'import initializeCloudSync from "@/shared/services/initializeCloudSync";\n'
        'import "@/lib/tokenHealthCheck"; // Proactive token health-check scheduler\n'
        "\n"
        'const isBuildPhase = process.env.NEXT_PHASE === "phase-production-build";\n'
        "\n"
        "// Initialize cloud sync when this module is imported\n"
        "let initialized = false;\n"
    )
    replace_once(path, old, new)

    old = (
        "export async function ensureCloudSyncInitialized() {\n"
        "  if (!initialized) {\n"
        "    try {\n"
        "      await initializeCloudSync();\n"
        "      initialized = true;\n"
        "    } catch (error) {\n"
        '      console.error("[ServerInit] Error initializing cloud sync:", error);\n'
        "    }\n"
        "  }\n"
        "  return initialized;\n"
        "}\n"
        "\n"
        "// Auto-initialize when module loads\n"
        'ensureCloudSyncInitialized().catch((err) => console.error("[CloudSync] ensure failed:", err));\n'
    )
    new = (
        "export async function ensureCloudSyncInitialized() {\n"
        "  if (isBuildPhase) return false;\n"
        "  if (!initialized) {\n"
        "    try {\n"
        "      await initializeCloudSync();\n"
        "      initialized = true;\n"
        "    } catch (error) {\n"
        '      console.error("[ServerInit] Error initializing cloud sync:", error);\n'
        "    }\n"
        "  }\n"
        "  return initialized;\n"
        "}\n"
        "\n"
        "// Auto-initialize when module loads\n"
        "if (!isBuildPhase) {\n"
        '  ensureCloudSyncInitialized().catch((err) => console.error("[CloudSync] ensure failed:", err));\n'
        "}\n"
    )
    replace_once(path, old, new)


def patch_root_routes(source_root: Path) -> None:
    page_path = source_root / "src" / "app" / "page.tsx"
    page_old = (
        '// Auto-initialize cloud sync when server starts\n'
        'import "@/lib/initCloudSync";\n'
        'import { redirect } from "next/navigation";\n'
        "\n"
        "export default function InitPage() {\n"
    )
    page_new = (
        '// Auto-initialize cloud sync when server starts\n'
        'import "@/lib/initCloudSync";\n'
        'import { redirect } from "next/navigation";\n'
        "\n"
        'export const dynamic = "force-dynamic";\n'
        "\n"
        "export default function InitPage() {\n"
    )
    replace_once(page_path, page_old, page_new)

    layout_path = source_root / "src" / "app" / "layout.tsx"
    layout_old = (
        'const inter = Inter({\n'
        '  subsets: ["latin"],\n'
        '  variable: "--font-inter",\n'
        "});\n"
        "\n"
        "export const metadata = {\n"
    )
    layout_new = (
        'const inter = Inter({\n'
        '  subsets: ["latin"],\n'
        '  variable: "--font-inter",\n'
        "});\n"
        "\n"
        'export const dynamic = "force-dynamic";\n'
        "\n"
        "export const metadata = {\n"
    )
    replace_once(layout_path, layout_old, layout_new)


def patch_next_config(source_root: Path) -> None:
    path = source_root / "next.config.mjs"
    old = (
        "/** @type {import('next').NextConfig} */\n"
        "const nextConfig = {\n"
        "  // Turbopack config: redirect native modules to stubs at build time\n"
    )
    new = (
        "/** @type {import('next').NextConfig} */\n"
        "const nextConfig = {\n"
        "  experimental: {\n"
        "    webpackBuildWorker: true,\n"
        "  },\n"
        "  // Turbopack config: redirect native modules to stubs at build time\n"
    )
    replace_once(path, old, new)


def patch_instrumentation_import(source_root: Path) -> None:
    path = source_root / "src" / "instrumentation.ts"
    old = (
        '  if (process.env.NEXT_RUNTIME === "nodejs") {\n'
        "    // Computed path prevents Turbopack from statically resolving the import\n"
        "    // for the Edge instrumentation bundle, avoiding spurious warnings about\n"
        "    // Node.js modules not being available in the Edge Runtime.\n"
        '    const nodeMod = "./instrumentation-" + "node";\n'
        "    const { registerNodejs } = await import(nodeMod);\n"
        "    await registerNodejs();\n"
        "  }\n"
    )
    new = (
        '  if (process.env.NEXT_RUNTIME === "nodejs") {\n'
        "    // Webpack standalone builds need a literal import so instrumentation-node\n"
        "    // is emitted into the server bundle instead of compiling to an empty\n"
        "    // runtime context module.\n"
        '    const { registerNodejs } = await import("./instrumentation-node");\n'
        "    await registerNodejs();\n"
        "  }\n"
    )
    replace_once(path, old, new)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: prepare_build_context.py <source_root>")

    source_root = Path(sys.argv[1]).resolve()
    patch_token_healthcheck(source_root)
    patch_cloud_sync_init(source_root)
    patch_root_routes(source_root)
    patch_next_config(source_root)
    patch_instrumentation_import(source_root)


if __name__ == "__main__":
    main()
