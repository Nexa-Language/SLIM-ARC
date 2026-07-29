'use strict';

const appleSplashScreenSizes = {
  'iPad Pro 12.9"': { width: 2048, height: 2732, scaleFactor: 2 },
  'iPad Pro 11"': { width: 1668, height: 2388, scaleFactor: 2 },
  'iPad Pro 10.5"': { width: 1668, height: 2388, scaleFactor: 2 },
  'iPad Pro 9.7"': { width: 1536, height: 2048, scaleFactor: 2 },
  'iPad Air 13"': { width: 2048, height: 2732, scaleFactor: 2 },
  'iPad Air 11"': { width: 1640, height: 2360, scaleFactor: 2 },
  'iPad Air 10.9"': { width: 1640, height: 2360, scaleFactor: 2 },
  'iPad Air 10.5"': { width: 1668, height: 2224, scaleFactor: 2 },
  'iPad Air 9.7"': { width: 1536, height: 2048, scaleFactor: 2 },
  'iPad 11"': { width: 1640, height: 2360, scaleFactor: 2 },
  'iPad 10.2"': { width: 1620, height: 2160, scaleFactor: 2 },
  'iPad 9.7"': { width: 1536, height: 2048, scaleFactor: 2 },
  'iPad mini 8.3"': { width: 1488, height: 2266, scaleFactor: 2 },
  'iPad mini 7.9"': { width: 1536, height: 2048, scaleFactor: 2 },
  "iPhone 16 Pro Max": { width: 1320, height: 2868, scaleFactor: 3 },
  "iPhone 16 Pro": { width: 1206, height: 2622, scaleFactor: 3 },
  "iPhone 16 Plus": { width: 1290, height: 2796, scaleFactor: 3 },
  "iPhone 16": { width: 1179, height: 2556, scaleFactor: 3 },
  "iPhone 16e": { width: 1170, height: 2532, scaleFactor: 3 },
  "iPhone 15 Pro Max": { width: 1290, height: 2796, scaleFactor: 3 },
  "iPhone 15 Pro": { width: 1179, height: 2556, scaleFactor: 3 },
  "iPhone 15 Plus": { width: 1290, height: 2796, scaleFactor: 3 },
  "iPhone 15": { width: 1179, height: 2556, scaleFactor: 3 },
  "iPhone 14 Pro Max": { width: 1290, height: 2796, scaleFactor: 3 },
  "iPhone 14 Pro": { width: 1179, height: 2556, scaleFactor: 3 },
  "iPhone 14 Plus": { width: 1284, height: 2778, scaleFactor: 3 },
  "iPhone 14": { width: 1170, height: 2532, scaleFactor: 3 },
  "iPhone 13 Pro Max": { width: 1284, height: 2778, scaleFactor: 3 },
  "iPhone 13 Pro": { width: 1170, height: 2532, scaleFactor: 3 },
  "iPhone 13": { width: 1170, height: 2532, scaleFactor: 3 },
  "iPhone 13 mini": { width: 1125, height: 2436, scaleFactor: 3 },
  "iPhone 12 Pro Max": { width: 1284, height: 2778, scaleFactor: 3 },
  "iPhone 12 Pro": { width: 1170, height: 2532, scaleFactor: 3 },
  "iPhone 12": { width: 1170, height: 2532, scaleFactor: 3 },
  "iPhone 12 mini": { width: 1125, height: 2436, scaleFactor: 3 },
  "iPhone 11 Pro Max": { width: 1242, height: 2688, scaleFactor: 3 },
  "iPhone 11 Pro": { width: 1125, height: 2436, scaleFactor: 3 },
  "iPhone 11": { width: 828, height: 1792, scaleFactor: 2 },
  "iPhone XS Max": { width: 1242, height: 2688, scaleFactor: 3 },
  "iPhone XS": { width: 1125, height: 2436, scaleFactor: 3 },
  "iPhone XR": { width: 828, height: 1792, scaleFactor: 2 },
  "iPhone X": { width: 1125, height: 2436, scaleFactor: 3 },
  "iPhone 8 Plus": { width: 1242, height: 2208, scaleFactor: 3 },
  "iPhone 8": { width: 750, height: 1334, scaleFactor: 2 },
  "iPhone 7 Plus": { width: 1242, height: 2208, scaleFactor: 3 },
  "iPhone 7": { width: 750, height: 1334, scaleFactor: 2 },
  "iPhone 6s Plus": { width: 1242, height: 2208, scaleFactor: 3 },
  "iPhone 6s": { width: 750, height: 1334, scaleFactor: 2 },
  "iPhone 6 Plus": { width: 1242, height: 2208, scaleFactor: 3 },
  "iPhone 6": { width: 750, height: 1334, scaleFactor: 2 },
  'iPhone SE 4.7"': { width: 750, height: 1334, scaleFactor: 2 },
  'iPhone SE 4"': { width: 640, height: 1136, scaleFactor: 2 },
  "iPod touch 5th generation and later": { width: 640, height: 1136, scaleFactor: 2 }
};
function defaultSplashScreenName(landscape, size, dark) {
  return `apple-splash-${landscape ? "landscape" : "portrait"}-${typeof dark === "boolean" ? dark ? "dark-" : "light-" : ""}${size.width}x${size.height}.png`;
}
const AllAppleDeviceNames = Array.from(Object.keys(appleSplashScreenSizes).map((k) => k));
function createAppleSplashScreens(options = {}, devices = AllAppleDeviceNames) {
  const {
    darkImageResolver,
    padding,
    resizeOptions,
    darkResizeOptions,
    linkMediaOptions,
    png,
    name
  } = options;
  return {
    darkImageResolver,
    sizes: devices.map((deviceName) => appleSplashScreenSizes[deviceName]),
    padding,
    resizeOptions,
    darkResizeOptions,
    linkMediaOptions,
    png,
    name
  };
}
function combinePresetAndAppleSplashScreens(preset, options = {}, devices = AllAppleDeviceNames) {
  return {
    ...preset,
    appleSplashScreens: createAppleSplashScreens(options, devices)
  };
}

exports.AllAppleDeviceNames = AllAppleDeviceNames;
exports.appleSplashScreenSizes = appleSplashScreenSizes;
exports.combinePresetAndAppleSplashScreens = combinePresetAndAppleSplashScreens;
exports.createAppleSplashScreens = createAppleSplashScreens;
exports.defaultSplashScreenName = defaultSplashScreenName;
