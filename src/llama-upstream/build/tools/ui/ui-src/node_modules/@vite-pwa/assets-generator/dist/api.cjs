'use strict';

const index = require('./index.cjs');
const favicon = require('./shared/assets-generator.D6uDklIq.cjs');
require('./shared/assets-generator.4HPlJg00.cjs');
require('sharp');
require('sharp-ico');



exports.createPngCompressionOptions = index.createPngCompressionOptions;
exports.createResizeOptions = index.createResizeOptions;
exports.defaultDarkResizeOptions = index.defaultDarkResizeOptions;
exports.defaultPngCompressionOptions = index.defaultPngCompressionOptions;
exports.defaultPngOptions = index.defaultPngOptions;
exports.defaultResizeOptions = index.defaultResizeOptions;
exports.createAppleSplashScreenHtmlLink = favicon.createAppleSplashScreenHtmlLink;
exports.createAppleTouchIconHtmlLink = favicon.createAppleTouchIconHtmlLink;
exports.createFaviconHtmlLink = favicon.createFaviconHtmlLink;
exports.createSharp = favicon.createSharp;
exports.extractAssetSize = favicon.extractAssetSize;
exports.generateFavicon = favicon.generateFavicon;
exports.generateMaskableAsset = favicon.generateMaskableAsset;
exports.generateTransparentAsset = favicon.generateTransparentAsset;
