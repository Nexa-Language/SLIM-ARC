import { existsSync, statSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import process from 'node:process';
import { createConfigLoader } from 'unconfig';
export { createPngCompressionOptions, createResizeOptions, defaultAssetName, defaultDarkResizeOptions, defaultPngCompressionOptions, defaultPngOptions, defaultResizeOptions } from './index.mjs';
export { A as AllAppleDeviceNames, a as appleSplashScreenSizes, b as combinePresetAndAppleSplashScreens, c as createAppleSplashScreens, d as defaultSplashScreenName } from './shared/assets-generator.CUAsp7yq.mjs';
export { minimalPreset } from './presets/minimal.mjs';
export { minimal2023Preset } from './presets/minimal-2023.mjs';

function defineConfig(config) {
  return config;
}
async function loadConfig(cwd = process.cwd(), configOrPath = cwd, extraConfigSources = [], defaults = { overrideAssets: true, logLevel: "info" }) {
  let inlineConfig = {};
  if (typeof configOrPath !== "string") {
    inlineConfig = configOrPath;
    if (inlineConfig.config === false) {
      return {
        config: inlineConfig,
        sources: []
      };
    } else {
      configOrPath = inlineConfig.config || process.cwd();
    }
  }
  const resolved = resolve(cwd, configOrPath);
  let isFile = false;
  if (existsSync(resolved) && statSync(resolved).isFile()) {
    isFile = true;
    cwd = dirname(resolved).replace(/\\/g, "/");
  }
  const loader = createConfigLoader({
    sources: isFile ? [
      {
        files: resolved,
        extensions: []
      }
    ] : [
      {
        files: [
          "pwa-assets.config"
        ]
      },
      ...extraConfigSources
    ],
    cwd,
    defaults: inlineConfig
  });
  const result = await loader.load();
  result.config = Object.assign(defaults, result.config || inlineConfig);
  return result;
}

export { defineConfig, loadConfig };
