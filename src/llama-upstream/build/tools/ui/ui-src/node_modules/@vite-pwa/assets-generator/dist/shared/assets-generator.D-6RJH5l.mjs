import { d as defaultSplashScreenName } from './assets-generator.CUAsp7yq.mjs';
import { toResolvedSize } from '../index.mjs';
import sharp from 'sharp';
import { encode } from 'sharp-ico';

function extractAssetSize(size, padding) {
  const width = typeof size.original === "number" ? size.original : size.original.width;
  const height = typeof size.original === "number" ? size.original : size.original.height;
  return {
    width: Math.round(width * (1 - padding)),
    height: Math.round(height * (1 - padding))
  };
}
async function createSharp(type, image, size, background, options, channels) {
  const { padding = 0 } = options ?? {};
  const useSize = toResolvedSize(size);
  const { width, height } = extractAssetSize(useSize, padding);
  const result = sharp({
    create: {
      width: useSize.width,
      height: useSize.height,
      channels: channels ?? 4,
      background
    }
  }).composite([{
    input: await sharp(image).resize(
      width,
      height,
      options?.resizeOptions
    ).toBuffer()
  }]);
  if (type === "none" || !options)
    return result;
  return type === "png" ? result.png(options.outputOptions) : result.webp(options.outputOptions);
}

function createFaviconHtmlLink(format, preset, icon) {
  const result = createFaviconLink(preset, icon);
  if (format === "string") {
    let favicon = `<link${icon.includeId ? ` id="${result.id}"` : ""} rel="${result.rel}" href="${result.href}"`;
    if (result.sizes)
      favicon += ` sizes="${result.sizes}"`;
    if (result.type)
      favicon += ` type="${result.type}"`;
    favicon += `${icon.xhtml ? " /" : ""}>`;
    return favicon;
  }
  return result;
}
function createAppleTouchIconHtmlLink(format, icon) {
  const href = `${icon.basePath ?? "/"}${icon.name}`;
  const { width, height } = toResolvedSize(icon.size);
  const id = `ati-${width}-${height}`;
  if (format === "string")
    return `<link${icon.includeId ? ` id="${id}"` : ""} rel="apple-touch-icon" href="${href}"${icon.xhtml ? " /" : ""}>`;
  return {
    id,
    rel: "apple-touch-icon",
    href
  };
}
function createAppleSplashScreenHtmlLink(format, options) {
  const link = createAppleSplashScreenLink(
    createRequiredHtmlLinkOptions(options)
  );
  return format === "string" ? `<link${options.includeId ? ` id="${link.id}"` : ""} rel="${link.rel}" media="${link.media}" href="${link.href}"${options.xhtml ? " /" : ""}>` : link;
}
function createFaviconLink(preset, icon) {
  const href = `${icon.basePath ?? "/"}${icon.name}`;
  if (icon.name.endsWith(".svg")) {
    if (preset === "2023") {
      return {
        id: "fav-svg",
        type: "image/svg+xml",
        href,
        rel: "icon",
        sizes: "any"
      };
    }
    return {
      id: "fav-svg",
      type: "image/svg+xml",
      href,
      rel: "icon"
    };
  }
  const { width, height } = toResolvedSize(icon.size);
  if (preset === "2023") {
    return {
      id: `fav-${width}x${height}`,
      href,
      rel: "icon",
      sizes: `${width}x${height}`
    };
  }
  return {
    id: `fav-${height}x${height}`,
    href,
    rel: "icon",
    sizes: "any"
  };
}
function createAppleSplashScreenLink(options) {
  const {
    size,
    landscape,
    addMediaScreen,
    name,
    basePath,
    dark
  } = options;
  const { width, height, scaleFactor } = size;
  const tokens = [
    `(device-width: ${(landscape ? height : width) / scaleFactor}px)`,
    `(device-height: ${(landscape ? width : height) / scaleFactor}px)`,
    `(-webkit-device-pixel-ratio: ${scaleFactor})`,
    `(orientation: ${landscape ? "landscape" : "portrait"})`
  ];
  if (dark)
    tokens.unshift("(prefers-color-scheme: dark)");
  if (addMediaScreen)
    tokens.unshift("screen");
  return {
    id: `atsi-${landscape ? height : width}-${landscape ? width : height}-${scaleFactor}-${dark ? "dark" : "light"}`,
    rel: "apple-touch-startup-image",
    media: tokens.join(" and "),
    href: `${basePath}${name(landscape, size, dark)}`
  };
}
function createRequiredHtmlLinkOptions(options) {
  return {
    size: options.size,
    landscape: options.landscape,
    addMediaScreen: options.addMediaScreen,
    name: options.name ?? defaultSplashScreenName,
    basePath: options.basePath ?? "/",
    dark: options.dark === true,
    includeId: options.includeId === true
  };
}

async function generateMaskableAsset(type, image, size, options) {
  return await createSharp(
    type,
    image,
    size,
    options?.resizeOptions?.background ?? "white",
    options,
    4
  );
}

async function generateTransparentAsset(type, image, size, options) {
  return await createSharp(
    type,
    image,
    size,
    { r: 0, g: 0, b: 0, alpha: 0 },
    options,
    4
  );
}

async function generateFavicon(format, image, options) {
  return encode([await sharp(image).toFormat(format, options).toBuffer()]);
}

export { createFaviconHtmlLink as a, createAppleTouchIconHtmlLink as b, createSharp as c, createAppleSplashScreenHtmlLink as d, extractAssetSize as e, generateTransparentAsset as f, generateMaskableAsset as g, generateFavicon as h };
