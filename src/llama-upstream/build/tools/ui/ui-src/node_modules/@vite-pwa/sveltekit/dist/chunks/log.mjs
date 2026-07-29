import { relative } from 'node:path';
import { cyan, magenta, green, dim, yellow } from 'kolorist';

const version = "1.1.0";

function logWorkboxResult(strategy, viteOptions, buildResult) {
  const { root, logLevel = "info" } = viteOptions;
  if (logLevel === "silent")
    return;
  if (!buildResult) {
    console.info([
      "",
      `${cyan(`SvelteKit VitePWA v${version}`)}`,
      `mode      ${magenta(strategy)}`
    ].join("\n"));
    return;
  }
  const { count, size, filePaths, warnings } = buildResult;
  if (logLevel === "info") {
    console.info([
      "",
      `${cyan(`SvelteKit VitePWA v${version}`)}`,
      `mode      ${magenta(strategy)}`,
      `precache  ${green(`${count} entries`)} ${dim(`(${(size / 1024).toFixed(2)} KiB)`)}`,
      "files generated",
      ...filePaths.map((p) => `  ${dim(relative(root, p))}`)
    ].join("\n"));
  }
  warnings && warnings.length > 0 && console.warn(yellow([
    "warnings",
    ...warnings.map((w) => `  ${w}`),
    ""
  ].join("\n")));
}

export { logWorkboxResult };
