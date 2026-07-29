import { G as GenerateOptionsType, c as ImageSourceInput, d as GenerateOptionsOptionType, e as GenerateFaviconType, f as GenerateFaviconOptionsType } from './shared/assets-generator.BQ3PQ6A_.js';
export { g as GenerateOptions, h as GenerateOutputOptions, k as IconAsset, I as ImageAssets, a as ImageAssetsInstructions, i as ManifestIcon, j as ManifestIcons, b as ManifestIconsOptionsType, M as ManifestIconsType } from './shared/assets-generator.BQ3PQ6A_.js';
import { R as ResolvedAssetSize, b as AssetSize } from './shared/assets-generator.DnoqiTld.js';
export { l as AppleSplahScreenHtmlLinkOptions, A as AppleSplashScreenLink, F as FaviconLink, k as HtmlIconLinkOptions, H as HtmlLink, a as HtmlLinkPreset, j as HtmlLinkReturnType, i as HtmlLinkType, o as createAppleSplashScreenHtmlLink, n as createAppleTouchIconHtmlLink, m as createFaviconHtmlLink, h as createPngCompressionOptions, g as createResizeOptions, c as defaultDarkResizeOptions, e as defaultPngCompressionOptions, f as defaultPngOptions, d as defaultResizeOptions } from './shared/assets-generator.DnoqiTld.js';
import * as sharp from 'sharp';
import sharp__default from 'sharp';
import 'unconfig';

declare function extractAssetSize(size: ResolvedAssetSize, padding: number): {
    width: number;
    height: number;
};
declare function createSharp<OutputType extends GenerateOptionsType>(type: OutputType, image: ImageSourceInput, size: AssetSize, background: sharp__default.Color, options?: GenerateOptionsOptionType<OutputType>, channels?: sharp__default.Channels): Promise<sharp__default.Sharp>;

declare function generateMaskableAsset<OutputType extends GenerateOptionsType>(type: OutputType, image: ImageSourceInput, size: AssetSize, options?: GenerateOptionsOptionType<OutputType>): Promise<sharp.Sharp>;

declare function generateTransparentAsset<OutputType extends GenerateOptionsType>(type: OutputType, image: ImageSourceInput, size: AssetSize, options?: GenerateOptionsOptionType<OutputType>): Promise<sharp.Sharp>;

declare function generateFavicon<Format extends GenerateFaviconType>(format: Format, image: ImageSourceInput, options?: GenerateFaviconOptionsType<Format>): Promise<Buffer>;

export { GenerateFaviconOptionsType, GenerateFaviconType, GenerateOptionsOptionType, GenerateOptionsType, ImageSourceInput, createSharp, extractAssetSize, generateFavicon, generateMaskableAsset, generateTransparentAsset };
