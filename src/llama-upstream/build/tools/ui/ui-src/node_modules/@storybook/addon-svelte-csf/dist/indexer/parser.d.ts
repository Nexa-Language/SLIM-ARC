import type { IndexInput } from 'storybook/internal/types';
import type { StorybookAddonSvelteCsFOptions } from '../preset.js';
interface Results {
    meta: Pick<IndexInput, 'title' | 'tags'>;
    stories: Array<Pick<IndexInput, 'exportName' | 'name' | 'tags'>>;
    isLegacy: boolean;
}
export declare function parseForIndexer(filename: string, options: Partial<StorybookAddonSvelteCsFOptions>): Promise<Results>;
export {};
