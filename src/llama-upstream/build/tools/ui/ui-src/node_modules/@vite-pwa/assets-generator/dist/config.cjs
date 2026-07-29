'use strict';

const node_fs = require('node:fs');
const node_path = require('node:path');
const process = require('node:process');
const unconfig = require('unconfig');
const index = require('./index.cjs');
const splash = require('./shared/assets-generator.4HPlJg00.cjs');
const presets_minimal = require('./presets/minimal.cjs');
const presets_minimal2023 = require('./presets/minimal-2023.cjs');

function _interopDefaultCompat (e) { return e && typeof e === 'object' && 'default' in e ? e.default : e; }

const process__default = /*#__PURE__*/_interopDefaultCompat(process);

function defineConfig(config) {
  return config;
}
async function loadConfig(cwd = process__default.cwd(), configOrPath = cwd, extraConfigSources = [], defaults = { overrideAssets: true, logLevel: "info" }) {
  let inlineConfig = {};
  if (typeof configOrPath !== "string") {
    inlineConfig = configOrPath;
    if (inlineConfig.config === false) {
      return {
        config: inlineConfig,
        sources: []
      };
    } else {
      configOrPath = inlineConfig.config || process__default.cwd();
    }
  }
  const resolved = node_path.resolve(cwd, configOrPath);
  let isFile = false;
  if (node_fs.existsSync(resolved) && node_fs.statSync(resolved).isFile()) {
    isFile = true;
    cwd = node_path.dirname(resolved).replace(/\\/g, "/");
  }
  const loader = unconfig.createConfigLoader({
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

exports.createPngCompressionOptions = index.createPngCompressionOptions;
exports.createResizeOptions = index.createResizeOptions;
exports.defaultAssetName = index.defaultAssetName;
exports.defaultDarkResizeOptions = index.defaultDarkResizeOptions;
exports.defaultPngCompressionOptions = index.defaultPngCompressionOptions;
exports.defaultPngOptions = index.defaultPngOptions;
exports.defaultResizeOptions = index.defaultResizeOptions;
exports.AllAppleDeviceNames = splash.AllAppleDeviceNames;
exports.appleSplashScreenSizes = splash.appleSplashScreenSizes;
exports.combinePresetAndAppleSplashScreens = splash.combinePresetAndAppleSplashScreens;
exports.createAppleSplashScreens = splash.createAppleSplashScreens;
exports.defaultSplashScreenName = splash.defaultSplashScreenName;
exports.minimalPreset = presets_minimal.minimalPreset;
exports.minimal2023Preset = presets_minimal2023.minimal2023Preset;
exports.defineConfig = defineConfig;
exports.loadConfig = loadConfig;
