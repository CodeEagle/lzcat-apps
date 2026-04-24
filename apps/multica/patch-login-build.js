import fs from "node:fs";

const sourceRoot = process.env.MULTICA_SOURCE_ROOT || "/app";
const path = `${sourceRoot}/packages/views/auth/login-page.tsx`;
const source = fs.readFileSync(path, "utf8");

const before = `onClick={() => {
                setStep("email");
                setCode("");
                setError("");
              }}`;

const after = `onClick={() => {
                window.location.href = "/";
              }}`;

if (!source.includes(before)) {
  throw new Error("expected login Back button handler not found");
}

fs.writeFileSync(path, source.replace(before, after));
console.log("Patched login Back button to return to home");
