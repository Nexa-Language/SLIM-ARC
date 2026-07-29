import { createResizeOptions, createPngCompressionOptions, toResolvedSize, defaultAssetName, defaultPngCompressionOptions, toResolvedAsset } from '../index.mjs';
import { d as defaultSplashScreenName } from '../shared/assets-generator.CUAsp7yq.mjs';
import { d as createAppleSplashScreenHtmlLink, g as generateMaskableAsset, f as generateTransparentAsset, a as createFaviconHtmlLink, b as createAppleTouchIconHtmlLink, h as generateFavicon } from '../shared/assets-generator.D-6RJH5l.mjs';
import 'sharp';
import 'sharp-ico';

function resolveAppleSplashScreensInstructions(image, imageAssets, instructions, useAppleSplashScreens) {
  const appleSplashScreens = resolveAppleSplashScreens(
    imageAssets,
    useAppleSplashScreens
  );
  if (!appleSplashScreens || !appleSplashScreens.sizes.length)
    return;
  const { linkMediaOptions, name: resolveName, sizes, png } = appleSplashScreens;
  const sizesMap = /* @__PURE__ */ new Map();
  const splashScreens = sizes.reduce((acc, size) => {
    if (sizesMap.get(size.width) === size.height)
      return acc;
    sizesMap.set(size.width, size.height);
    const { width: height, height: width, ...restSize } = size;
    const {
      width: lheight,
      height: lwidth,
      ...restResizeOptions
    } = size.resizeOptions || {};
    const landscapeSize = {
      ...restSize,
      width,
      height,
      resizeOptions: {
        ...restResizeOptions,
        width: lwidth,
        height: lheight
      }
    };
    acc.push({
      size,
      landscape: false,
      dark: size.darkResizeOptions ? false : void 0,
      resizeOptions: size.resizeOptions,
      padding: size.padding ?? 0.3,
      png: size.png ?? png
    });
    acc.push({
      size: landscapeSize,
      landscape: true,
      dark: size.darkResizeOptions ? false : void 0,
      resizeOptions: landscapeSize.resizeOptions,
      padding: size.padding ?? 0.3,
      png: size.png ?? png
    });
    if (size.darkResizeOptions) {
      const {
        width: dlheight,
        height: dlwidth,
        ...restDarkResizeOptions
      } = size.darkResizeOptions;
      const landscapeDarkResizeOptions = { ...restDarkResizeOptions, width: dlwidth, height: dlheight };
      const landscapeDarkSize = {
        ...restSize,
        width,
        height,
        resizeOptions: landscapeDarkResizeOptions,
        darkResizeOptions: void 0
      };
      acc.push({
        size,
        landscape: false,
        dark: true,
        resizeOptions: size.darkResizeOptions,
        padding: size.padding ?? 0.3,
        png: size.png ?? png
      });
      acc.push({
        size: landscapeDarkSize,
        landscape: true,
        dark: true,
        resizeOptions: landscapeDarkResizeOptions,
        padding: size.padding ?? 0.3,
        png: size.png ?? png
      });
    }
    return acc;
  }, []);
  sizesMap.clear();
  const cache = {};
  const originalName = imageAssets.originalName;
  const imageResolver = (dark) => {
    if (!dark || typeof appleSplashScreens.darkImageResolver !== "function")
      return Promise.resolve(image);
    const cached = cache[originalName];
    if (cached)
      return cached;
    return cache[originalName] = appleSplashScreens.darkImageResolver(originalName).then((darkImage) => Promise.resolve(darkImage ?? image));
  };
  for (const size of splashScreens) {
    const basePath = linkMediaOptions.basePath;
    const name = resolveName(size.landscape, size.size, size.dark);
    const url = `${basePath}${name}`;
    const promise = () => imageResolver(size.dark === true).then((i) => generateMaskableAsset("png", i, size.size, {
      padding: size.padding,
      resizeOptions: {
        ...size.resizeOptions,
        background: size.resizeOptions?.background ?? (size.dark ? "black" : "white")
      },
      outputOptions: size.png
    }));
    instructions.appleSplashScreen[url] = {
      name,
      url,
      width: size.size.width,
      height: size.size.height,
      mimeType: "image/png",
      link: createAppleSplashScreenHtmlLink("string", {
        size: size.size,
        landscape: size.landscape,
        addMediaScreen: linkMediaOptions.addMediaScreen,
        xhtml: linkMediaOptions.xhtml,
        name: resolveName,
        basePath,
        dark: size.dark,
        includeId: imageAssets.htmlLinks.includeId
      }),
      linkObject: createAppleSplashScreenHtmlLink("link", {
        size: size.size,
        landscape: size.landscape,
        addMediaScreen: linkMediaOptions.addMediaScreen,
        xhtml: linkMediaOptions.xhtml,
        name: resolveName,
        basePath,
        dark: size.dark,
        includeId: imageAssets.htmlLinks.includeId
      }),
      buffer: () => promise().then((m) => m.toBuffer())
    };
  }
}
function resolveAppleSplashScreens(imageAssets, useAppleSplashScreens) {
  let appleSplashScreens;
  if (useAppleSplashScreens) {
    const {
      padding = 0.3,
      resizeOptions: useResizeOptions = {},
      darkResizeOptions: useDarkResizeOptions,
      linkMediaOptions: useLinkMediaOptions = {},
      sizes,
      name = defaultSplashScreenName,
      png: usePng = {},
      darkImageResolver
    } = useAppleSplashScreens;
    const resizeOptions = createResizeOptions(false, useResizeOptions);
    const darkResizeOptions = useDarkResizeOptions ? createResizeOptions(true, useDarkResizeOptions) : void 0;
    const png = createPngCompressionOptions(usePng);
    for (const size of sizes) {
      if (typeof size.padding === "undefined")
        size.padding = padding;
      if (typeof size.png === "undefined")
        size.png = png;
      if (typeof size.resizeOptions === "undefined")
        size.resizeOptions = resizeOptions;
      if (typeof size.darkResizeOptions === "undefined" && darkResizeOptions)
        size.darkResizeOptions = darkResizeOptions;
    }
    const {
      log = true,
      addMediaScreen = true,
      basePath = imageAssets.basePath ?? "/",
      xhtml = false
    } = useLinkMediaOptions;
    appleSplashScreens = {
      darkImageResolver,
      padding,
      sizes,
      linkMediaOptions: {
        log,
        addMediaScreen,
        basePath,
        xhtml
      },
      name,
      png
    };
  }
  return appleSplashScreens;
}

function resolveTransparentIcons(imageAssets, image, assets, htmlPreset, instructions) {
  const asset = assets.assets.transparent;
  const { sizes, padding, resizeOptions } = asset;
  const { basePath, htmlLinks: { xhtml, includeId } } = imageAssets;
  for (const size of sizes) {
    const name = assets.assetName("transparent", size);
    const url = `${basePath}${name}`;
    const promise = () => generateTransparentAsset("png", image, size, {
      padding,
      resizeOptions,
      outputOptions: assets.png
    });
    instructions.transparent[url] = {
      name,
      url,
      width: size.width,
      height: size.height,
      mimeType: "image/png",
      buffer: () => promise().then((m) => m.toBuffer())
    };
  }
  const favicons = asset.favicons;
  if (!favicons)
    return;
  for (const [size, name] of favicons) {
    const url = `${basePath}${name}`;
    const promise = () => generateTransparentAsset("png", image, size, {
      padding,
      resizeOptions,
      outputOptions: assets.png
    }).then((m) => m.toBuffer()).then((b) => generateFavicon("png", b));
    const resolvedSize = toResolvedSize(size);
    instructions.favicon[url] = {
      name,
      url,
      width: resolvedSize.width,
      height: resolvedSize.height,
      mimeType: "image/x-icon",
      link: createFaviconHtmlLink("string", htmlPreset, {
        name,
        size,
        basePath,
        xhtml,
        includeId
      }),
      linkObject: createFaviconHtmlLink("link", htmlPreset, {
        name,
        size,
        basePath,
        xhtml,
        includeId
      }),
      buffer: () => promise()
    };
  }
}
function resolveMaskableIcons(type, imageAssets, image, assets, htmlPreset, instructions) {
  const asset = assets.assets[type];
  const { sizes, padding, resizeOptions } = asset;
  const { basePath, htmlLinks: { xhtml, includeId } } = imageAssets;
  for (const size of sizes) {
    const name = assets.assetName(type, size);
    const url = `${basePath}${name}`;
    const promise = () => generateMaskableAsset("png", image, size, {
      padding,
      resizeOptions,
      outputOptions: assets.png
    });
    const buffer = () => promise().then((m) => m.toBuffer());
    if (type === "apple") {
      instructions.apple[url] = {
        name,
        url,
        width: size.width,
        height: size.height,
        mimeType: "image/png",
        link: createAppleTouchIconHtmlLink("string", {
          name,
          size,
          basePath,
          xhtml,
          includeId
        }),
        linkObject: createAppleTouchIconHtmlLink("link", {
          name,
          size,
          basePath,
          xhtml,
          includeId
        }),
        buffer
      };
    } else {
      instructions.maskable[url] = {
        name,
        url,
        width: size.width,
        height: size.height,
        mimeType: "image/png",
        buffer
      };
    }
  }
  const favicons = asset.favicons;
  if (!favicons)
    return;
  for (const [size, name] of favicons) {
    const url = `${basePath}${name}`;
    const resolvedSize = toResolvedSize(size);
    instructions.favicon[url] = {
      name,
      url,
      width: resolvedSize.width,
      height: resolvedSize.height,
      mimeType: "image/x-icon",
      link: createFaviconHtmlLink("string", htmlPreset, {
        name,
        size,
        basePath,
        xhtml,
        includeId
      }),
      linkObject: createFaviconHtmlLink("link", htmlPreset, {
        name,
        size,
        basePath,
        xhtml,
        includeId
      }),
      buffer: () => generateMaskableAsset("png", image, size, {
        padding,
        resizeOptions,
        outputOptions: assets.png
      }).then((m) => m.toBuffer()).then((b) => generateFavicon("png", b))
    };
  }
}

async function resolveInstructions(imageAssets) {
  const {
    imageResolver,
    imageName,
    originalName,
    preset = "minimal",
    faviconPreset
  } = imageAssets;
  const [usePreset, htmlPreset] = await resolvePreset(preset, faviconPreset);
  const {
    assetName = defaultAssetName,
    png = defaultPngCompressionOptions,
    appleSplashScreens: useAppleSplashScreens
  } = usePreset;
  const assets = {
    assets: {
      transparent: toResolvedAsset("transparent", usePreset.transparent),
      maskable: toResolvedAsset("maskable", usePreset.maskable),
      apple: toResolvedAsset("apple", usePreset.apple)
    },
    png,
    assetName
  };
  const instructions = {
    image: imageName,
    originalName,
    favicon: {},
    transparent: {},
    maskable: {},
    apple: {},
    appleSplashScreen: {}
  };
  const image = await imageResolver();
  resolveTransparentIcons(imageAssets, image, assets, htmlPreset, instructions);
  resolveMaskableIcons("maskable", imageAssets, image, assets, htmlPreset, instructions);
  resolveMaskableIcons("apple", imageAssets, image, assets, htmlPreset, instructions);
  if (imageName.endsWith(".svg")) {
    const name = imageAssets.resolveSvgName(imageName);
    const url = `${imageAssets.basePath}${name}`;
    instructions.favicon[url] = {
      name,
      url,
      width: 0,
      height: 0,
      mimeType: "image/svg+xml",
      link: createFaviconHtmlLink("string", htmlPreset, {
        name,
        basePath: imageAssets.basePath,
        xhtml: imageAssets.htmlLinks.xhtml,
        includeId: imageAssets.htmlLinks.includeId
      }),
      linkObject: createFaviconHtmlLink("link", htmlPreset, {
        name,
        basePath: imageAssets.basePath,
        xhtml: imageAssets.htmlLinks.xhtml,
        includeId: imageAssets.htmlLinks.includeId
      }),
      buffer: () => Promise.resolve(image)
    };
  }
  resolveAppleSplashScreensInstructions(image, imageAssets, instructions, useAppleSplashScreens);
  return instructions;
}
async function resolvePreset(preset, faviconPreset) {
  const htmlLinkPreset = faviconPreset ?? "default";
  if (typeof preset === "object")
    return [preset, htmlLinkPreset];
  switch (preset) {
    case "minimal":
      return [await import('../presets/minimal.mjs').then((m) => m.minimalPreset), htmlLinkPreset];
    case "minimal-2023":
      return [await import('../presets/minimal-2023.mjs').then((m) => m.minimal2023Preset), faviconPreset ?? "2023"];
    default:
      throw new Error(`Preset ${preset} not yet implemented`);
  }
}

export { resolveInstructions };
