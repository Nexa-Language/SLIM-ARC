/* eslint-disable @typescript-eslint/no-explicit-any */
import StoryComponent from './runtime/Story.svelte';
// TODO: Remove in next major release
import LegacyMetaComponent from './runtime/LegacyMeta.svelte';
// TODO: Remove in next major release
import LegacyStoryComponent from './runtime/LegacyStory.svelte';
// TODO: Remove in next major release
import LegacyTemplateComponent from './runtime/LegacyTemplate.svelte';
export function defineMeta(_meta) {
    return {
        Story: StoryComponent,
    };
}
// TODO: Remove in next major release
export { 
/**
 * @deprecated Use `defineMeta` instead
 * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#meta-component-removed-in-favor-of-definemeta}
 */
LegacyMetaComponent as Meta, 
/**
 * @deprecated Use `Story` component returned from `defineMeta` instead
 * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#export-meta-removed-in-favor-of-definemeta}
 */
LegacyStoryComponent as Story, 
/**
 * @deprecated Use snippets instead
 * @see {@link https://github.com/storybookjs/addon-svelte-csf/blob/main/MIGRATION.md#template-component-removed}
 */
LegacyTemplateComponent as Template, };
