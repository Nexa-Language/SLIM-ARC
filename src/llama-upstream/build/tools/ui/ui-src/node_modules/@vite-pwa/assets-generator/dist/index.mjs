const defaultResizeOptions = {
  fit: "contain",
  background: "white"
};
const defaultDarkResizeOptions = {
  fit: "contain",
  background: "black"
};
const defaultPngCompressionOptions = {
  compressionLevel: 9,
  quality: 60
};
const defaultPngOptions = {
  transparent: { padding: 0.05, resizeOptions: { fit: "contain", background: "transparent" } },
  maskable: { padding: 0.3, resizeOptions: { fit: "contain", background: "white" } },
  apple: { padding: 0.3, resizeOptions: { fit: "contain", background: "white" } }
};
function createResizeOptions(dark, options) {
  return {
    ...dark ? defaultDarkResizeOptions : defaultResizeOptions,
    ...options
  };
}
function createPngCompressionOptions(options) {
  return {
    ...defaultPngCompressionOptions,
    ...options
  };
}

function toResolvedSize(size) {
  return {
    original: size,
    width: typeof size === "number" ? size : size.width,
    height: typeof size === "number" ? size : size.height
  };
}
function toResolvedAsset(type, asset) {
  return {
    padding: defaultPngOptions[type].padding,
    resizeOptions: defaultPngOptions[type].resizeOptions,
    ...asset,
    sizes: asset.sizes.map(toResolvedSize)
  };
}
function defaultAssetName(type, size) {
  switch (type) {
    case "transparent":
      return `pwa-${size.width}x${size.height}.png`;
    case "maskable":
      return `maskable-icon-${size.width}x${size.height}.png`;
    case "apple":
      return `apple-touch-icon-${size.width}x${size.height}.png`;
  }
}
function sameAssetSize(a, b) {
  if (typeof a === "number" && typeof b.original === "number")
    return a === b.original;
  if (typeof a !== "number" && typeof b.original !== "number")
    return a.width === b.width && a.height === b.height;
  return false;
}
function cloneResolvedAssetsSizes({ png, assetName, assets }) {
  return {
    assets: {
      transparent: cloneResolvedAssetSizes(assets.transparent),
      maskable: cloneResolvedAssetSizes(assets.maskable),
      apple: cloneResolvedAssetSizes(assets.apple)
    },
    png,
    assetName
  };
}
function cloneResolvedAssetSizes({ sizes, ...asset }) {
  return {
    ...asset,
    sizes: [...sizes]
  };
}

export { cloneResolvedAssetSizes, cloneResolvedAssetsSizes, createPngCompressionOptions, createResizeOptions, defaultAssetName, defaultDarkResizeOptions, defaultPngCompressionOptions, defaultPngOptions, defaultResizeOptions, sameAssetSize, toResolvedAsset, toResolvedSize };
