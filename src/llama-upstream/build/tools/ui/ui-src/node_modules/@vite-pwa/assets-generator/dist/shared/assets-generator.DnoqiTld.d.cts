import * as sharp from 'sharp';
import { PngOptions, ResizeOptions } from 'sharp';
import { LoadConfigSource, LoadConfigResult } from 'unconfig';

type HtmlLinkPreset = 'default' | '2023';
interface HtmlLink {
    id: string;
    rel: 'apple-touch-startup-image' | 'apple-touch-icon' | 'icon';
    href: string;
}
interface AppleSplashScreenLink extends HtmlLink {
    media: string;
}
interface FaviconLink extends HtmlLink {
    sizes?: string;
    type?: string;
}
type HtmlLinkType = 'string' | 'link';
type HtmlLinkReturnType<T, R extends HtmlLink> = T extends 'string' ? string : T extends 'link' ? R : never;
interface HtmlIconLinkOptions {
    name: string;
    /**
     * Required only for non SVG favicon
     */
    size?: AssetSize;
    xhtml?: boolean;
    basePath?: string;
    /**
     * Render the id attribute when using string format?
     *
     * The id will always be present in object notation.
     *
     * @default false
     */
    includeId?: boolean;
}
interface AppleSplahScreenHtmlLinkOptions {
    size: AppleDeviceSize;
    landscape: boolean;
    addMediaScreen: boolean;
    xhtml?: boolean;
    name?: AppleSplashScreenName;
    basePath?: string;
    dark?: boolean;
    /**
     * Render the id attribute when using string format?
     *
     * The id will always be present in object notation.
     *
     * @default false
     */
    includeId?: boolean;
}
declare function createFaviconHtmlLink<Format extends HtmlLinkType>(format: Format, preset: HtmlLinkPreset, icon: HtmlIconLinkOptions): HtmlLinkReturnType<Format, FaviconLink>;
declare function createAppleTouchIconHtmlLink<Format extends HtmlLinkType>(format: Format, icon: HtmlIconLinkOptions): HtmlLinkReturnType<Format, HtmlLink>;
declare function createAppleSplashScreenHtmlLink<Format extends HtmlLinkType>(format: Format, options: AppleSplahScreenHtmlLinkOptions): HtmlLinkReturnType<Format, AppleSplashScreenLink>;

declare const defaultResizeOptions: {
    fit: "contain";
    background: string;
};
declare const defaultDarkResizeOptions: {
    fit: "contain";
    background: string;
};
declare const defaultPngCompressionOptions: PngOptions;
declare const defaultPngOptions: Record<AssetType, {
    padding: number;
    resizeOptions: ResizeOptions;
}>;
declare function createResizeOptions(dark: boolean, options: ResizeOptions): {
    width?: number | undefined;
    height?: number | undefined;
    fit: keyof sharp.FitEnum;
    position?: number | string | undefined;
    background: sharp.Color;
    kernel?: keyof sharp.KernelEnum | undefined;
    withoutEnlargement?: boolean | undefined;
    withoutReduction?: boolean | undefined;
    fastShrinkOnLoad?: boolean | undefined;
};
declare function createPngCompressionOptions(options: PngOptions): {
    progressive?: boolean | undefined;
    compressionLevel?: number | undefined;
    adaptiveFiltering?: boolean | undefined;
    quality?: number | undefined;
    effort?: number | undefined;
    palette?: boolean | undefined;
    colours?: number | undefined;
    colors?: number | undefined;
    dither?: number | undefined;
    force?: boolean | undefined;
};

interface Preset extends Assets {
}

/**
 * Minimal preset.
 *
 * @deprecated use `minimal-2023` instead
 * @see https://www.leereamsnyder.com/favicons-in-2021
 */
declare const minimalPreset: Preset;

/**
 * Minimal preset for 2023.
 *
 * @see https://dev.to/masakudamatsu/favicon-nightmare-how-to-maintain-sanity-3al7
 */
declare const minimal2023Preset: Preset;

type AppleDeviceName = 'iPad Pro 12.9"' | 'iPad Pro 11"' | 'iPad Pro 10.5"' | 'iPad Pro 9.7"' | 'iPad Air 13"' | 'iPad Air 11"' | 'iPad Air 10.9"' | 'iPad Air 10.5"' | 'iPad Air 9.7"' | 'iPad 11"' | 'iPad 10.2"' | 'iPad 9.7"' | 'iPad mini 8.3"' | 'iPad mini 7.9"' | 'iPhone 16 Pro Max' | 'iPhone 16 Pro' | 'iPhone 16 Plus' | 'iPhone 16' | 'iPhone 16e' | 'iPhone 15 Pro Max' | 'iPhone 15 Pro' | 'iPhone 15 Plus' | 'iPhone 15' | 'iPhone 14 Pro Max' | 'iPhone 14 Pro' | 'iPhone 14 Plus' | 'iPhone 14' | 'iPhone 13 Pro Max' | 'iPhone 13 Pro' | 'iPhone 13' | 'iPhone 13 mini' | 'iPhone 12 Pro Max' | 'iPhone 12 Pro' | 'iPhone 12' | 'iPhone 12 mini' | 'iPhone 11 Pro Max' | 'iPhone 11 Pro' | 'iPhone 11' | 'iPhone XS Max' | 'iPhone XS' | 'iPhone XR' | 'iPhone X' | 'iPhone 8 Plus' | 'iPhone 8' | 'iPhone 7 Plus' | 'iPhone 7' | 'iPhone 6s Plus' | 'iPhone 6s' | 'iPhone 6 Plus' | 'iPhone 6' | 'iPhone SE 4.7"' | 'iPhone SE 4"' | 'iPod touch 5th generation and later';
interface AppleSplashScreen extends Record<AppleDeviceName, AppleDeviceSize> {
}
/**
 * Apple device names and resolutions.
 * @see https://developer.apple.com/design/human-interface-guidelines/layout#iOS-iPadOS-device-screen-dimensions
 */
declare const appleSplashScreenSizes: AppleSplashScreen;
declare function defaultSplashScreenName(landscape: boolean, size: AppleDeviceSize, dark?: boolean): string;
declare const AllAppleDeviceNames: AppleDeviceName[];
declare function createAppleSplashScreens(options?: {
    /**
     * The image to use for generating dark apple splash screens assets.
     *
     * By default, it will use the original image.
     *
     * @param imageName The image name configured in images.
     */
    darkImageResolver?: (imageName: string) => Promise<Buffer | undefined>;
    padding?: number;
    resizeOptions?: ResizeOptions;
    darkResizeOptions?: ResizeOptions;
    linkMediaOptions?: AppleTouchStartupImageOptions;
    png?: PngOptions;
    name?: AppleSplashScreenName;
}, devices?: AppleDeviceName[]): {
    darkImageResolver: ((imageName: string) => Promise<Buffer | undefined>) | undefined;
    sizes: AppleDeviceSize[];
    padding: number | undefined;
    resizeOptions: ResizeOptions | undefined;
    darkResizeOptions: ResizeOptions | undefined;
    linkMediaOptions: AppleTouchStartupImageOptions | undefined;
    png: PngOptions | undefined;
    name: AppleSplashScreenName | undefined;
};
declare function combinePresetAndAppleSplashScreens(preset: Preset, options?: {
    /**
     * The image to use for generating dark apple splash screens assets.
     *
     * By default, it will use the original image.
     *
     * @param imageName The image name configured in images.
     */
    darkImageResolver?: (imageName: string) => Promise<Buffer | undefined>;
    padding?: number;
    resizeOptions?: ResizeOptions;
    darkResizeOptions?: ResizeOptions;
    linkMediaOptions?: AppleTouchStartupImageOptions;
    png?: PngOptions;
    name?: AppleSplashScreenName;
}, devices?: AppleDeviceName[]): {
    appleSplashScreens: {
        darkImageResolver: ((imageName: string) => Promise<Buffer | undefined>) | undefined;
        sizes: AppleDeviceSize[];
        padding: number | undefined;
        resizeOptions: ResizeOptions | undefined;
        darkResizeOptions: ResizeOptions | undefined;
        linkMediaOptions: AppleTouchStartupImageOptions | undefined;
        png: PngOptions | undefined;
        name: AppleSplashScreenName | undefined;
    };
    png?: PngOptions;
    assetName?: (type: AssetType, size: ResolvedAssetSize) => string;
    transparent: Asset;
    maskable: Asset;
    apple: Asset;
};

declare function toResolvedSize(size: AssetSize): {
    original: AssetSize;
    width: number;
    height: number;
};
declare function toResolvedAsset(type: AssetType, asset: Asset): {
    sizes: {
        original: AssetSize;
        width: number;
        height: number;
    }[];
    padding: number;
    resizeOptions: sharp.ResizeOptions;
    favicons?: Favicon[];
};
declare function defaultAssetName(type: AssetType, size: ResolvedAssetSize): string;
declare function sameAssetSize(a: AssetSize, b: ResolvedAssetSize): boolean;
declare function cloneResolvedAssetsSizes({ png, assetName, assets }: ResolvedAssets): {
    assets: {
        transparent: {
            sizes: ResolvedAssetSize[];
            favicons?: Favicon[];
            padding: number;
            resizeOptions: sharp.ResizeOptions;
        };
        maskable: {
            sizes: ResolvedAssetSize[];
            favicons?: Favicon[];
            padding: number;
            resizeOptions: sharp.ResizeOptions;
        };
        apple: {
            sizes: ResolvedAssetSize[];
            favicons?: Favicon[];
            padding: number;
            resizeOptions: sharp.ResizeOptions;
        };
    };
    png: sharp.PngOptions;
    assetName: (type: AssetType, size: ResolvedAssetSize) => string;
};
declare function cloneResolvedAssetSizes({ sizes, ...asset }: ResolvedAsset): {
    sizes: ResolvedAssetSize[];
    favicons?: Favicon[];
    padding: number;
    resizeOptions: sharp.ResizeOptions;
};

/**
 * Built-in presets.
 * - `minimal-2023`: Only generate the bare minimum assets.
 * - `minimal`: Only generate the bare minimum assets (deprecated).
 * - `android`: Generate assets for Android.
 * - `windows`: Generate assets for Windows.
 * - `ios`: Generate assets for iOS.
 * - `all`: `android`, `windows` and `ios` presets combined.
 */
type BuiltInPreset = 'minimal' | 'minimal-2023' | 'android' | 'windows' | 'ios' | 'all';
interface HeadLinkOptions {
    /**
     * Base path to generate the html head links.
     *
     * @default '/'
     */
    basePath?: string;
    /**
     * The preset to use.
     *
     * If using the built-in presets from CLI (`minimal` or `minimal-2023`), this option will be ignored (will be set to `default` or `2023` for `minimal` and `minimal-2023` respectively).
     *
     * @default 'default'
     */
    preset?: HtmlLinkPreset;
    /**
     * By default, the SVG favicon will use the SVG file name as the name.
     *
     * For example, if you provide `public/logo.svg` as the image source, the href in the link will be `<basePath>logo.svg`.
     *
     * @param name The name of the SVG icons.
     */
    resolveSvgName?: (name: string) => string;
    /**
     * Generate an id when generating the html head links.
     *
     * @default false
     */
    xhtml?: boolean;
    /**
     * Include the id when generating the html head links.
     *
     * @default false
     */
    includeId?: boolean;
}
interface UserConfig {
    /**
     * Project root directory. Can be an absolute path, or a path relative from
     * the location of the config file itself.
     * @default process.cwd()
     */
    root?: string;
    /**
     * Path to the config file.
     *
     * Default resolving to `pwa-assets.config.[js|mjs|cjs]`
     *
     * Setting to `false` will disable config resolving.
     */
    config?: string | false;
    /**
     * Override assets?
     *
     * @default true
     */
    overrideAssets?: boolean;
    /**
     * Log level.
     *
     * @default 'info'
     */
    logLevel?: LogLevel;
    /**
     * Path relative to `root` where to find the images to use for generating PWA assets.
     *
     * PWA Assets will be generated in the same directory.
     */
    images?: string | string[];
    /**
     * Preset to use.
     *
     * @default 'minimal'
     */
    preset?: BuiltInPreset | Preset;
    /**
     * Options for generating the html head links for `apple-touch-icon` and favicons.
     */
    headLinkOptions?: HeadLinkOptions;
    /**
     * Show the PWA web manifest icons' entry.
     *
     * @default true
     */
    manifestIconsEntry?: boolean;
}
interface ResolvedConfig extends Required<Omit<UserConfig, 'preset'>> {
    preset: Preset;
}
declare function defineConfig(config: UserConfig): UserConfig;
declare function loadConfig<U extends UserConfig>(cwd?: string, configOrPath?: string | U, extraConfigSources?: LoadConfigSource[], defaults?: UserConfig): Promise<LoadConfigResult<U>>;

/**
 * Icon size.
 */
type AssetSize = number | {
    width: number;
    height: number;
};
/**
 * Icon size with resolved width and height.
 */
interface ResolvedAssetSize {
    original: AssetSize;
    width: number;
    height: number;
}
/**
 * Favicon size and name.
 */
type Favicon = [size: AssetSize, name: string];
interface Asset {
    sizes: AssetSize[];
    padding?: number;
    resizeOptions?: ResizeOptions;
    favicons?: Favicon[];
}
interface AppleDeviceSize {
    width: number;
    height: number;
    scaleFactor: number;
    /**
     * The padding to add to the splash screen.
     *
     * @default 0.3
     */
    padding?: number;
    /**
     * @default { compressionLevel: 9, quality: 60 }
     */
    png?: PngOptions;
    /**
     * Resize options: by default, `sharp` will use white background color.
     */
    resizeOptions?: ResizeOptions;
    /**
     * Dark resize options.
     *
     * If you want to also add a dark splash screen, change the background color with this another option.
     */
    darkResizeOptions?: ResizeOptions;
}
type AppleSplashScreenName = (landscape: boolean, size: AppleDeviceSize, dark?: boolean) => string;
interface AppleTouchStartupImageOptions {
    /**
     * Show the html head links?
     *
     * @default true
     */
    log?: boolean;
    /**
     * Base path to generate the html head links.
     *
     * @default '/'
     */
    basePath?: string;
    /**
     * Add media screen to the `apple-touch-startup-image` rel link?
     *
     * @default true
     */
    addMediaScreen?: boolean;
    /**
     * Using XHTML?
     *
     * @default false
     */
    xhtml?: boolean;
}
interface AppleSplashScreens {
    /**
     * The image to use for generating dark apple splash screens assets.
     *
     * By default, it will use the original image.
     *
     * @param imageName The image name configured in images.
     */
    darkImageResolver?: (imageName: string) => Promise<Buffer | undefined>;
    sizes: AppleDeviceSize[];
    /**
     * The padding to add to the splash screen.
     *
     * @default 0.3
     */
    padding?: number;
    /**
     * Global png options.
     *
     * @default { compressionLevel: 9, quality: 60 }
     */
    png?: PngOptions;
    /**
     * Resize options: by default, `sharp` will use white background color.
     */
    resizeOptions?: ResizeOptions;
    /**
     * Dark resize options.
     *
     * If you want to also add a dark splash screen, change the background color with this another option.
     */
    darkResizeOptions?: ResizeOptions;
    /**
     * Options to generate the html head links.
     */
    linkMediaOptions?: AppleTouchStartupImageOptions;
    /**
     * Customize the splash screen name.
     *
     * @param landscape Is the splash screen landscape?
     * @param size The splash screen size.
     * @param dark Is the splash screen dark?
     * @returns The splash screen name.
     *
     * @default (landscape, size, dark?: boolean) => `apple-splash-${landscape ? 'landscape' : 'portrait'}-${typeof dark === 'boolean' ? (dark ? 'dark-' : 'light-') : ''}${size.width}x${size.height}.png`
     */
    name?: AppleSplashScreenName;
}
interface ResolvedAppleSplashScreens {
    darkImageResolver?: (imageName: string) => Promise<Buffer | undefined>;
    padding: number;
    sizes: AppleDeviceSize[];
    linkMediaOptions: Required<AppleTouchStartupImageOptions>;
    name: AppleSplashScreenName;
    png: PngOptions;
}
type AssetType = 'transparent' | 'maskable' | 'apple';
interface ResolvedAsset extends Required<Omit<Asset, 'favicons' | 'sizes'>> {
    sizes: ResolvedAssetSize[];
    favicons?: Favicon[];
}
interface Assets extends Record<AssetType, Asset> {
    /**
     * @default { compressionLevel: 9, quality: 60 }
     */
    png?: PngOptions;
    /**
     * @default `pwa-<width>x<height>.png`, `maskable-icon-<width>x<height>.png`, `apple-touch-icon-<width>x<height>.png`
     */
    assetName?: (type: AssetType, size: ResolvedAssetSize) => string;
    /**
     * Splash screens.
     */
    appleSplashScreens?: AppleSplashScreens;
}
interface ResolvedAssets {
    assets: Record<AssetType, ResolvedAsset>;
    png: PngOptions;
    /**
     * @default `pwa-<width>x<height>.png`, `maskable-icon-<width>x<height>.png`, `apple-touch-icon-<width>x<height>.png`
     */
    assetName: (type: AssetType, size: ResolvedAssetSize) => string;
}
type LogLevel = 'info' | 'warn' | 'silent';
interface BuildOptions {
    root: string;
    logLevel?: LogLevel;
    overrideAssets?: boolean;
    headLinkOptions: Required<HeadLinkOptions>;
}
interface ResolvedBuildOptions extends Required<BuildOptions> {
}

export { cloneResolvedAssetsSizes as $, AllAppleDeviceNames as C, createAppleSplashScreens as D, combinePresetAndAppleSplashScreens as E, toResolvedSize as Y, toResolvedAsset as Z, sameAssetSize as _, cloneResolvedAssetSizes as a0, defaultDarkResizeOptions as c, defaultResizeOptions as d, defaultPngCompressionOptions as e, defaultPngOptions as f, createResizeOptions as g, createPngCompressionOptions as h, createFaviconHtmlLink as m, createAppleTouchIconHtmlLink as n, createAppleSplashScreenHtmlLink as o, minimalPreset as p, minimal2023Preset as q, defineConfig as t, loadConfig as u, defaultAssetName as v, appleSplashScreenSizes as y, defaultSplashScreenName as z };
export type { AppleSplashScreenLink as A, BuiltInPreset as B, FaviconLink as F, Favicon as G, HtmlLink as H, Asset as I, AppleDeviceSize as J, AppleSplashScreenName as K, AppleTouchStartupImageOptions as L, AppleSplashScreens as M, ResolvedAppleSplashScreens as N, AssetType as O, Preset as P, ResolvedAsset as Q, ResolvedAssetSize as R, Assets as S, ResolvedAssets as T, UserConfig as U, LogLevel as V, BuildOptions as W, ResolvedBuildOptions as X, HtmlLinkPreset as a, AssetSize as b, HtmlLinkType as i, HtmlLinkReturnType as j, HtmlIconLinkOptions as k, AppleSplahScreenHtmlLinkOptions as l, HeadLinkOptions as r, ResolvedConfig as s, AppleDeviceName as w, AppleSplashScreen as x };
