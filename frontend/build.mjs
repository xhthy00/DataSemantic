import { build } from "esbuild";
import postcss from "postcss";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const assets = fileURLToPath(
  new URL("../src/wren_semantic/static/", import.meta.url),
);
// Keep editor styles inside the business workspace; Ant Design owns the admin shell.
const editor = postcss.parse(
  await readFile(new URL("./src/editor.css", import.meta.url), "utf8"),
);
editor.walkRules((rule) => {
  if (rule.parent.type === "atrule" && /keyframes$/.test(rule.parent.name))
    return;
  rule.selector = postcss.list
    .comma(rule.selector)
    .map((selector) => {
      if (selector === ":root" || selector.startsWith("body")) return selector;
      if (selector.startsWith("dialog"))
        return selector.replace(/^dialog/, "#modal");
      if (
        selector.startsWith("#toast") ||
        selector.startsWith("#modal") ||
        selector.startsWith(".skip-link")
      )
        return selector;
      return `:where(.studio-editor, #modal) ${selector}`;
    })
    .join(",");
});
await writeFile(`${assets}editor.css`, editor.toString());
await build({
  absWorkingDir: root,
  entryPoints: ["src/studio-controller.js"],
  outfile: `${assets}studio.js`,
  bundle: true,
  minify: true,
  target: ["es2022"],
  format: "esm",
  jsx: "automatic",
  define: { "process.env.NODE_ENV": '"production"' },
  legalComments: "linked",
  metafile: true,
}).then(async (result) => {
  const outputs = Object.entries(result.metafile.outputs).map(
    ([file, info]) =>
      `${file.split("/").pop()}: ${(info.bytes / 1024).toFixed(1)} kB`,
  );
  console.log(`Built Ant Design admin: ${outputs.join(", ")}`);
});
