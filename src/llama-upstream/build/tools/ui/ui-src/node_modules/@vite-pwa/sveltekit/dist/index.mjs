import { VitePWA } from 'vite-plugin-pwa';
import { resolve, join } from 'node:path';
import { mkdir, rm, readFile, writeFile, rename, lstat } from 'node:fs/promises';
import { glob } from 'tinyglobby';

function configureSvelteKitOptions(kit, viteOptions, options) {
  const {
    base = viteOptions.base ?? "/",
    adapterFallback,
    outDir = `${viteOptions.root}/.svelte-kit`,
    assets = "static"
  } = kit;
  if (typeof options.includeManifestIcons === "undefined")
    options.includeManifestIcons = false;
  let config;
  if (options.strategies === "injectManifest") {
    if (!options.srcDir)
      options.srcDir = "src";
    if (!options.filename)
      options.filename = "service-worker.js";
    options.injectManifest = options.injectManifest ?? {};
    config = options.injectManifest;
  } else {
    options.workbox = options.workbox ?? {};
    if (!("navigateFallback" in options.workbox))
      options.workbox.navigateFallback = adapterFallback ?? base;
    config = options.workbox;
  }
  if (!config.globDirectory)
    config.globDirectory = `${outDir}/output`;
  let buildAssetsDir = kit.appDir ?? "_app/";
  if (buildAssetsDir[0] === "/")
    buildAssetsDir = buildAssetsDir.slice(1);
  if (buildAssetsDir[buildAssetsDir.length - 1] !== "/")
    buildAssetsDir += "/";
  if (!config.modifyURLPrefix) {
    config.globPatterns = buildGlobPatterns(config.globPatterns);
    if (kit.includeVersionFile)
      config.globPatterns.push(`client/${buildAssetsDir}version.json`);
  }
  config.globIgnores = buildGlobIgnores(config.globIgnores);
  if (!("dontCacheBustURLsMatching" in config))
    config.dontCacheBustURLsMatching = new RegExp(`${buildAssetsDir}immutable/`);
  if (!config.manifestTransforms) {
    config.manifestTransforms = [createManifestTransform(
      base,
      config.globDirectory,
      options.strategies === "injectManifest" ? void 0 : options.manifestFilename ?? "manifest.webmanifest",
      kit
    )];
  }
  if (options.pwaAssets) {
    options.pwaAssets.integration = {
      baseUrl: base,
      publicDir: resolve(viteOptions.root, assets),
      outDir: resolve(outDir, "output/client")
    };
  }
}
function createManifestTransform(base, outDir, webManifestName, options) {
  return async (entries) => {
    const defaultAdapterFallback = "prerendered/fallback.html";
    const suffix = options?.trailingSlash === "always" ? "/" : "";
    let adapterFallback = options?.adapterFallback;
    let excludeFallback = false;
    if (!adapterFallback) {
      adapterFallback = defaultAdapterFallback;
      excludeFallback = true;
    }
    const manifest = entries.filter(({ url }) => !(excludeFallback && url === defaultAdapterFallback)).map((e) => {
      let url = e.url;
      if (url.startsWith("client/"))
        url = url.slice(7);
      else if (url.startsWith("prerendered/dependencies/"))
        url = url.slice(25);
      else if (url.startsWith("prerendered/pages/"))
        url = url.slice(18);
      else if (url === defaultAdapterFallback)
        url = adapterFallback;
      if (url.endsWith(".html")) {
        if (url.startsWith("/"))
          url = url.slice(1);
        if (url === "index.html") {
          url = base;
        } else {
          const idx = url.lastIndexOf("/");
          if (idx > -1) {
            if (url.endsWith("/index.html"))
              url = `${url.slice(0, idx)}${suffix}`;
            else
              url = `${url.substring(0, url.lastIndexOf("."))}${suffix}`;
          } else {
            url = `${url.substring(0, url.lastIndexOf("."))}${suffix}`;
          }
        }
      }
      e.url = url;
      return e;
    });
    if (options?.spa && options?.adapterFallback) {
      const name = typeof options.spa === "object" && options.spa.fallbackMapping ? options.spa.fallbackMapping : options.adapterFallback;
      if (typeof options.spa === "object" && typeof options.spa.fallbackRevision === "function") {
        manifest.push({
          url: name,
          revision: await options.spa.fallbackRevision(),
          size: 0
        });
      } else {
        manifest.push(await buildManifestEntry(
          name,
          resolve(outDir, "client/_app/version.json")
        ));
      }
    }
    if (!webManifestName)
      return { manifest };
    return { manifest: manifest.filter((e) => e.url !== webManifestName) };
  };
}
function buildGlobPatterns(globPatterns) {
  if (globPatterns) {
    if (!globPatterns.some((g) => g.startsWith("prerendered/")))
      globPatterns.push("prerendered/**/*.{html,json}");
    if (!globPatterns.some((g) => g.startsWith("client/")))
      globPatterns.push("client/**/*.{js,css,ico,png,svg,webp,webmanifest}");
    if (!globPatterns.some((g) => g.includes("webmanifest")))
      globPatterns.push("client/*.webmanifest");
    return globPatterns;
  }
  return ["client/**/*.{js,css,ico,png,svg,webp,webmanifest}", "prerendered/**/*.{html,json}"];
}
function buildGlobIgnores(globIgnores) {
  if (globIgnores) {
    if (!globIgnores.some((g) => g.startsWith("server/")))
      globIgnores.push("server/**");
    return globIgnores;
  }
  return ["server/**"];
}
async function buildManifestEntry(url, path) {
  const [crypto, createReadStream] = await Promise.all([
    import('node:crypto').then((m) => m.default),
    import('node:fs').then((m) => m.createReadStream)
  ]);
  return new Promise((resolve2, reject) => {
    const cHash = crypto.createHash("MD5");
    const stream = createReadStream(path);
    stream.on("error", (err) => {
      reject(err);
    });
    stream.on("data", (chunk) => {
      cHash.update(chunk);
    });
    stream.on("end", () => {
      return resolve2({
        url,
        size: 0,
        revision: `${cHash.digest("hex")}`
      });
    });
  });
}

function SvelteKitPlugin(options, apiResolver) {
  let viteConfig;
  return {
    name: "vite-plugin-pwa:sveltekit:build",
    apply: "build",
    enforce: "pre",
    configResolved(config) {
      viteConfig = config;
    },
    async generateBundle(_, bundle) {
      if (viteConfig.build.ssr)
        return;
      const api = apiResolver();
      if (!api)
        return;
      const assetsGenerator = await api.pwaAssetsGenerator();
      if (assetsGenerator)
        assetsGenerator.injectManifestIcons();
      api.generateBundle(bundle, this);
    },
    writeBundle: {
      sequential: true,
      enforce: "pre",
      async handler() {
        const api = apiResolver();
        if (!api || viteConfig.build.ssr)
          return;
        const assetsGenerator = await api.pwaAssetsGenerator();
        if (assetsGenerator)
          await assetsGenerator.generate();
      }
    },
    closeBundle: {
      sequential: true,
      enforce: "pre",
      async handler() {
        const api = apiResolver();
        if (api && !api.disabled && viteConfig.build.ssr) {
          const webManifest = options.manifestFilename ?? "manifest.webmanifest";
          let swName = options.filename ?? "sw.js";
          const outDir = options.outDir ?? `${viteConfig.root}/.svelte-kit/output`;
          const clientOutputDir = join(outDir, "client");
          await mkdir(clientOutputDir, { recursive: true });
          if (!options.strategies || options.strategies === "generateSW" || options.selfDestroying) {
            let path;
            let existsFile;
            if (options.selfDestroying && options.strategies === "injectManifest") {
              if (swName.endsWith(".ts"))
                swName = swName.replace(/\.ts$/, ".js");
              path = join(clientOutputDir, "service-worker.js").replace("\\/g", "/");
              existsFile = await isFile(path);
              if (existsFile)
                await rm(path);
            }
            await api.generateSW();
            const serverOutputDir = join(outDir, "server");
            path = join(serverOutputDir, swName).replace(/\\/g, "/");
            existsFile = await isFile(path);
            if (existsFile) {
              const sw = await readFile(path, "utf-8");
              await writeFile(
                join(clientOutputDir, swName).replace("\\/g", "/"),
                sw,
                "utf-8"
              );
              await rm(path);
            }
            const result = await glob({
              patterns: ["workbox-*.js"],
              cwd: serverOutputDir,
              onlyFiles: true,
              expandDirectories: false
            });
            if (result && result.length > 0) {
              path = join(serverOutputDir, result[0]).replace(/\\/g, "/");
              await writeFile(
                join(clientOutputDir, result[0]).replace("\\/g", "/"),
                await readFile(path, "utf-8"),
                "utf-8"
              );
              await rm(path);
            }
            path = join(serverOutputDir, webManifest).replace(/\\/g, "/");
            existsFile = await isFile(path);
            if (existsFile)
              await rm(path);
            return;
          }
          if (swName.endsWith(".ts"))
            swName = swName.replace(/\.ts$/, ".js");
          const injectionPoint = !options.injectManifest || !("injectionPoint" in options.injectManifest) || !!options.injectManifest.injectionPoint;
          if (injectionPoint) {
            const injectManifestOptions = {
              globDirectory: outDir.replace(/\\/g, "/"),
              ...options.injectManifest ?? {},
              swSrc: join(clientOutputDir, "service-worker.js").replace(/\\/g, "/"),
              swDest: join(clientOutputDir, "service-worker.js").replace(/\\/g, "/")
            };
            const [injectManifest, logWorkboxResult] = await Promise.all([
              import('workbox-build').then((m) => m.injectManifest),
              import('./chunks/log.mjs').then((m) => m.logWorkboxResult)
            ]);
            const buildResult = await injectManifest(injectManifestOptions);
            logWorkboxResult("injectManifest", viteConfig, buildResult);
            if (swName !== "service-worker.js") {
              await rename(
                join(clientOutputDir, "service-worker.js").replace("\\/g", "/"),
                join(clientOutputDir, swName).replace("\\/g", "/")
              );
            }
          } else {
            const { logWorkboxResult } = await import('./chunks/log.mjs');
            logWorkboxResult("injectManifest", viteConfig);
            if (swName !== "service-worker.js") {
              await rename(
                join(clientOutputDir, "service-worker.js").replace("\\/g", "/"),
                join(clientOutputDir, swName).replace("\\/g", "/")
              );
            }
          }
        }
      }
    }
  };
}
async function isFile(path) {
  try {
    const stats = await lstat(path);
    return stats.isFile();
  } catch {
    return false;
  }
}

function SvelteKitPWA(userOptions = {}) {
  if (!userOptions.integration)
    userOptions.integration = {};
  userOptions.integration.closeBundleOrder = "pre";
  userOptions.integration.configureOptions = (viteConfig, options) => configureSvelteKitOptions(
    userOptions.kit ?? {},
    viteConfig,
    options
  );
  const plugins = VitePWA(userOptions);
  const plugin = plugins.find((p) => p && typeof p === "object" && "name" in p && p.name === "vite-plugin-pwa");
  const resolveVitePluginPWAAPI = () => {
    return plugin?.api;
  };
  return [
    // remove the build plugin: we're using a custom one
    ...plugins.filter((p) => p && typeof p === "object" && "name" in p && p.name !== "vite-plugin-pwa:build"),
    SvelteKitPlugin(userOptions, resolveVitePluginPWAAPI)
  ];
}

export { SvelteKitPWA };
